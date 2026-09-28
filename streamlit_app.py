"""
streamlit_app.py - The chat web page that customers see.

WHAT THIS FILE DOES
-------------------
Builds the chatbot's web page using Streamlit, a Python library that
turns a script into a web app. Start it with:

    streamlit run streamlit_app.py

IMPORTANT STREAMLIT IDEA: every time the user clicks something or sends a
message, Streamlit re-runs this whole file from top to bottom. Anything
that must survive between re-runs (like the chat history) is kept in
"st.session_state", a memory box that belongs to this browser tab.

Page layout:
  - Sidebar : pick a demo customer, see whether the AI is connected,
              count of specialist handoffs, and a "New conversation" button.
  - Main    : title, disclaimer, past messages, suggestion buttons,
              and the chat input box.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from supportbot.graph import DEFAULT_HF_MODEL, build_support_graph
from supportbot.observability import telemetry_mode
from supportbot.service import run_support_request
from supportbot.tools import DEMO_CUSTOMERS

# Read private settings (such as HF_TOKEN) from the ".env" file in the project
# folder and make them available as environment variables. Values already set
# in the terminal take priority over the file.
load_dotenv()


# Browser tab title and icon, and a centred (narrow) page layout.
st.set_page_config(
    page_title="Northstar customer care",
    page_icon=":material/support_agent:",
    layout="centered",
)

# Create the memory slots the first time the page loads (later re-runs keep them):
#   messages - the chat so far, as a list of {"role": ..., "content": ...}
#   handoffs - how many times this chat was passed to a specialist
st.session_state.setdefault("messages", [])
st.session_state.setdefault("handoffs", 0)

# Read settings from environment variables:
#   HF_MODEL - which Hugging Face model to use (defaults to Llama-3.1-8B-Instruct)
#   HF_TOKEN - your Hugging Face access token. If present, the AI is switched
#              on; if absent, the app runs in simulation mode.
model_name = os.getenv("HF_MODEL", DEFAULT_HF_MODEL)
llm_enabled = bool(os.getenv("HF_TOKEN"))


# @st.cache_resource: build the chatbot flowchart once and reuse it on every
# re-run, instead of rebuilding it after every click (which would be slow).
@st.cache_resource
def get_graph(model: str, use_llm: bool):
    """
    INPUT:  model   - AI model name, e.g. "meta-llama/Llama-3.1-8B-Instruct"
            use_llm - True if a Hugging Face token is available
    OUTPUT: the ready-to-run chatbot flowchart (see graph.py)
    """
    return build_support_graph(model_name=model, use_llm=use_llm)


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### :material/account_balance: Northstar")
    st.caption("Digital banking support")

    # Dropdown to choose which fake customer we are pretending to be.
    # It shows "Alex Morgan (CUST-1001)" but stores just "CUST-1001".
    customer_id = st.selectbox(
        "Demo customer",
        options=list(DEMO_CUSTOMERS),
        format_func=lambda key: f"{DEMO_CUSTOMERS[key]['name']} ({key})",
    )

    # Coloured badge: green "LLM connected" or blue "Simulation mode".
    st.badge(
        "LLM connected" if llm_enabled else "Simulation mode",
        icon=":material/online_prediction:" if llm_enabled else ":material/science:",
        color="green" if llm_enabled else "blue",
    )
    st.caption(f"Model: {model_name}" if llm_enabled else "Set HF_TOKEN to enable the LLM")
    st.caption(f"Observability: {telemetry_mode()}")

    # Counter showing how many specialist handoffs happened in this chat.
    st.metric("Specialist handoffs", st.session_state.handoffs)

    # "New conversation" button: wipe the chat and counter, then redraw the page.
    if st.button("New conversation", icon=":material/refresh:", width="stretch"):
        st.session_state.messages = []
        st.session_state.handoffs = 0
        st.rerun()
    st.caption("Demo only. Never enter real account numbers, passwords, PINs, or card details.")


# ---------------------------------------------------------------------------
# MAIN AREA - heading and disclaimer
# ---------------------------------------------------------------------------
st.title("How can we help?")
st.caption("Ask about an account, a loan estimate, or card support.")
st.warning(
    "This prototype uses fictional data. Loan estimates are illustrative, not an offer or financial advice.",
    icon=":material/info:",
)

# Quick-start buttons: the button label (left) and the message it sends (right).
suggestions = {
    "Check my account": "Show me my account balance and recent activity.",
    "Loan estimate": "Can you estimate my loan eligibility?",
    "Card support": "What is the status of my card?",
    "Talk to a person": "I need to speak with a specialist.",
}

# Because the page re-runs from the top each time, redraw every earlier
# message. Bot replies also show a small caption with the team name and trace ID.
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and message.get("route"):
            st.caption(f"{message['route']} | {message['trace_id']}")

# Show the suggestion buttons only on an empty chat (before the first message).
suggestion = None
if not st.session_state.messages:
    suggestion = st.pills(
        "Common requests",
        options=list(suggestions),
        label_visibility="collapsed",
    )

# The text box at the bottom. "prompt" holds what the user typed, or None.
# submit_mode="disable" greys the box out while a reply is being prepared.
prompt = st.chat_input("Message Northstar", submit_mode="disable")
# If a suggestion button was clicked, use its full message as the prompt.
if suggestion:
    prompt = suggestions[suggestion]


# ---------------------------------------------------------------------------
# HANDLE A NEW MESSAGE
# ---------------------------------------------------------------------------
if prompt:
    # 1. Save and show the customer's message.
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. Get the chatbot and gather recent history for context: up to the
    #    8 messages before the one just sent ([:-1] leaves out the new one).
    graph = get_graph(model_name, llm_enabled)
    history = [
        {"role": item["role"], "content": item["content"]}
        for item in st.session_state.messages[:-1][-8:]
    ]

    # 3. Run the chatbot, showing a progress indicator while it works.
    with st.chat_message("assistant", avatar=":material/support_agent:"):
        with st.status("Working on your request", type="compact") as status:
            with st.status("Routing to the right team", type="step"):
                # This is where the real work happens (see service.py).
                result = run_support_request(
                    graph=graph,
                    message=prompt,
                    customer_id=customer_id,
                    history=history,
                )
            with st.status("Preparing a grounded response", type="step"):
                response = result["response"]
            # Change the progress label to show which team answered.
            status.update(
                label=f"Handled by {result['route_label']}",
                state="complete",
            )

        # 4. Show the reply, with the team name and trace ID underneath.
        st.markdown(response)
        st.caption(f"{result['route_label']} | trace {result['trace_id']}")
        # If the AI failed and a backup template was used, say so.
        if result.get("model_warning"):
            st.caption("The configured model was unavailable; a safe demo response was used.")
        # If escalated, bump the sidebar counter and show the handoff ticket number.
        if result["escalated"]:
            st.session_state.handoffs += 1
            st.info(
                f"Simulated specialist handoff created: `{result['handoff_id']}`. "
                "A production deployment must connect this to an authenticated case-management queue."
            )

    # 5. Save the bot's reply so it is redrawn on the next re-run.
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": response,
            "route": result["route_label"],
            "trace_id": result["trace_id"],
        }
    )
