import streamlit as st
from src.llm import parse_user_intent, generate_chat_response
from src.fetcher import fetch_float_data
from src.visualizer import plot_depth_profile, plot_position_map
from src.db import get_floats_in_bounding_box, get_all_active_floats

st.set_page_config(
    page_title="SIQVA - Deep Ocean",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 🌊 Deep Ocean Bioluminescence CSS
st.markdown(
    """
    <style>
    /* Font Import */
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Space Grotesk', sans-serif !important;
    }
    
    /* Pure Black Background with subtle radial glow at the bottom */
    .stApp { 
        background: radial-gradient(circle at center bottom, #050D1A 0%, #000000 70%); 
        color: #E8F4F8; 
    }
    
    /* Glowing Headers */
    h1, h2, h3 {
        color: #00FF9F !important;
        font-weight: 700 !important;
        text-shadow: 0 0 15px rgba(0, 255, 159, 0.4);
    }
    
    .stCaption { 
        color: rgba(232, 244, 248, 0.6) !important; 
    }
    
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: #030811 !important;
        border-right: 1px solid rgba(0, 255, 159, 0.2) !important;
        box-shadow: 5px 0 20px rgba(0, 255, 159, 0.05);
    }
    
    /* Chat Input - Glowing Border */
    .stChatInputContainer {
        border-radius: 12px !important;
        background-color: #050D1A !important;
        border: 1px solid rgba(0, 255, 159, 0.3) !important;
        box-shadow: 0 0 15px rgba(0, 255, 159, 0.1) !important;
    }
    .stChatInputContainer:focus-within {
        border: 1px solid #00FF9F !important;
        box-shadow: 0 0 20px rgba(0, 255, 159, 0.3) !important;
    }

    /* Chat Messages - Dark Navy Cards */
    [data-testid="stChatMessage"] {
        background-color: #050D1A;
        border: 1px solid rgba(0, 255, 159, 0.15);
        border-radius: 12px;
        padding: 1rem 1.5rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 15px rgba(0, 255, 159, 0.05);
        transition: all 0.3s ease;
    }
    [data-testid="stChatMessage"]:hover {
        border: 1px solid rgba(0, 255, 159, 0.3);
        box-shadow: 0 4px 20px rgba(0, 255, 159, 0.15);
    }
    
    /* Expanders & Alerts */
    .stAlert, [data-testid="stExpander"] {
        background-color: #050D1A !important;
        color: #E8F4F8 !important;
        border: 1px solid rgba(0, 255, 159, 0.2) !important;
        border-radius: 8px !important;
    }
    
    /* Neon Scrollbar */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #000000; }
    ::-webkit-scrollbar-thumb { background: rgba(0, 255, 159, 0.3); border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #00FF9F; box-shadow: 0 0 10px #00FF9F; }
    
    /* Radio Buttons & Buttons Accent */
    div.stRadio > div { color: #E8F4F8; }
    </style>
    """,
    unsafe_allow_html=True
)

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {"role": "assistant", "content": "SIQVA Terminal Active. Monitoring ARGO network telemetry. Awaiting query..."}
    ]
if "active_wmo" not in st.session_state:
    st.session_state["active_wmo"] = None

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("SIQVA Core")
st.sidebar.caption("Deep Ocean Telemetry")

page = st.sidebar.radio("Navigation", ["Terminal (Chat)", "Global Matrix (Map)"])

st.sidebar.divider()

if st.session_state["active_wmo"]:
    st.sidebar.success(f"TARGET LOCKED:\nFloat {st.session_state['active_wmo']}")
    if st.sidebar.button("Release Target"):
        st.session_state["active_wmo"] = None
        st.rerun()
else:
    st.sidebar.info("No float targeted.")

# ==========================================
# PAGE 1: GLOBAL MAP EXPLORER
# ==========================================
if page == "Global Matrix (Map)":
    st.title("Global Matrix")
    st.caption("Active ARGO nodes across the world's oceans.")

    all_floats = get_all_active_floats()
    if all_floats:
        global_fig = plot_position_map(all_floats, "Global Network")
        global_fig.update_layout(height=700, margin={"r":0,"t":40,"l":0,"b":0})
        
        event = st.plotly_chart(
            global_fig, 
            use_container_width=True, 
            on_select="rerun", 
            selection_mode="points",
            key="global_map_fullscreen"
        )
        
        if event and hasattr(event, "selection") and event.selection.get("points"):
            clicked_wmo = event.selection["points"][0].get("hovertext")
            if clicked_wmo and st.session_state["active_wmo"] != int(clicked_wmo):
                st.session_state["active_wmo"] = int(clicked_wmo)
                st.rerun()

# ==========================================
# PAGE 2: CHAT ASSISTANT
# ==========================================
elif page == "Terminal (Chat)":
    st.title("Terminal")
    st.caption("Query the ocean database using natural language.")

    # Render history
    for i, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if "fig" in msg:
                st.plotly_chart(msg["fig"], use_container_width=True, key=f"history_chart_{i}")

    # Process prompt
    if user_prompt := st.chat_input("Enter command or query..."):
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.write(user_prompt)

        with st.spinner("Processing telemetry..."):
            parsed_intent = parse_user_intent(user_prompt)
            
        intent_type = parsed_intent.get("intent", "general_chat")
        variable = parsed_intent.get("variable", "TEMP")
        
        wmo_id = parsed_intent.get("wmo_id")
        if not wmo_id and st.session_state.get("active_wmo"):
            wmo_id = st.session_state["active_wmo"]
        
        with st.chat_message("assistant"):
            if intent_type == "depth_profile":
                if not wmo_id and parsed_intent.get("bounding_box"):
                    bbox = parsed_intent["bounding_box"]
                    loc_name = parsed_intent.get("location_name", "the requested region")
                    st.write(f"Scanning region: {loc_name}...")
                    floats = get_floats_in_bounding_box(bbox[0], bbox[1], bbox[2], bbox[3], limit=5)
                    
                    if floats:
                        wmo_id = floats[0]['float_wmo']
                        st.write(f"Target acquired: Float {wmo_id}.")
                    else:
                        err_msg = f"No active nodes found in {loc_name}."
                        st.write(err_msg)
                        st.session_state.messages.append({"role": "assistant", "content": err_msg})
                
                if wmo_id:
                    var_name = "Salinity" if variable == "PSAL" else "Temperature"
                    with st.spinner("Downloading node data..."):
                        df = fetch_float_data(wmo_id)

                    if not df.empty:
                        fig = plot_depth_profile(df, wmo_id, variable)
                        if fig:
                            reply_text = f"{var_name} profile generated for float {wmo_id}:"
                            st.write(reply_text)
                            st.plotly_chart(fig, use_container_width=True, key=f"chart_{len(st.session_state.messages)}")
                            st.session_state.messages.append({"role": "assistant", "content": reply_text, "fig": fig})
                    else:
                        err_msg = f"Telemetry unavailable for float {wmo_id}."
                        st.write(err_msg)
                        st.session_state.messages.append({"role": "assistant", "content": err_msg})
                        
            elif intent_type == "position_map":
                if parsed_intent.get("bounding_box"):
                    bbox = parsed_intent["bounding_box"]
                    loc_name = parsed_intent.get("location_name", "the requested region")
                    floats = get_floats_in_bounding_box(bbox[0], bbox[1], bbox[2], bbox[3], limit=500)
                    
                    if floats:
                        fig = plot_position_map(floats, loc_name)
                        reply_text = f"Located {len(floats)} active nodes in {loc_name}."
                        st.write(reply_text)
                        st.plotly_chart(fig, use_container_width=True, key=f"map_{len(st.session_state.messages)}")
                        st.session_state.messages.append({"role": "assistant", "content": reply_text, "fig": fig})
                    else:
                        err_msg = f"No active nodes found in {loc_name}."
                        st.write(err_msg)
                        st.session_state.messages.append({"role": "assistant", "content": err_msg})
                else:
                    err_msg = "Coordinates required. Specify a region (e.g., 'Arabian Sea')."
                    st.write(err_msg)
                    st.session_state.messages.append({"role": "assistant", "content": err_msg})

            else:
                ollama_msgs = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages if m["role"] in ["user", "assistant"] and "fig" not in m]
                with st.spinner("Analyzing..."):
                    response = generate_chat_response(ollama_msgs)
                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})