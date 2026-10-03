import streamlit as st
from src.llm import parse_user_intent, generate_chat_response
from src.fetcher import fetch_float_data
from src.visualizer import plot_depth_profile

st.set_page_config(page_title="SIQVA - Ocean AI Assistant", layout="wide")

st.title("🌊 SIQVA: Oceanographic Conversational Platform")
st.caption("Powered by Local Ollama & ARGO Real-time Telemetry")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {"role": "assistant", "content": "Hello! I am SIQVA. Ask me any oceanography question or request a float profile (e.g., 'Plot temperature profile for float 2902795' or 'Show salinity for 2902795')."}
    ]

# Render persistent chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "fig" in msg:
            st.plotly_chart(msg["fig"], use_container_width=True)

# Process user prompt
if user_prompt := st.chat_input("Type your question or request float data..."):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.write(user_prompt)

    # Process input using the LLM Intent Router
    with st.spinner("Analyzing intent..."):
        parsed_intent = parse_user_intent(user_prompt)
        
    intent_type = parsed_intent.get("intent", "general_chat")
    wmo_id = parsed_intent.get("wmo_id")
    variable = parsed_intent.get("variable", "TEMP")
    
    with st.chat_message("assistant"):
        if intent_type == "plot_profile" and wmo_id:
            var_name = "Salinity" if variable == "PSAL" else "Temperature"
            st.write(f"🔍 Recognized request to plot **{var_name}** for Float WMO `{wmo_id}`. Fetching data...")
            
            with st.spinner("Downloading ARGO dataset via argopy..."):
                df = fetch_float_data(wmo_id)

            if not df.empty:
                fig = plot_depth_profile(df, wmo_id, variable)
                reply_text = f"Here is the {var_name.lower()} profile for float **{wmo_id}**:"
                st.write(reply_text)
                st.plotly_chart(fig, use_container_width=True)
                st.session_state.messages.append({"role": "assistant", "content": reply_text, "fig": fig})
            else:
                err_msg = f"Could not retrieve data for float `{wmo_id}`. Please verify the ID."
                st.write(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})
        else:
            # Standard Conversational Call
            ollama_msgs = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages if m["role"] in ["user", "assistant"]]
            with st.spinner("Thinking..."):
                response = generate_chat_response(ollama_msgs)
            st.write(response)
            st.session_state.messages.append({"role": "assistant", "content": response})