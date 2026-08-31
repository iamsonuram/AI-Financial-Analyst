import html
from datetime import date

import streamlit as st

from ui.styles import load_css
from analysis.analysis_engine import AnalysisEngine
from database.filter_loader import FilterLoader
from agents.analyst_orchestrator import AnalystOrchestrator
from agents.data_chatbot import DataChatbot
from agents.sql_agent import build_date_period


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="AI Financial Analyst",
    page_icon="📊",
    layout="wide",
)

st.markdown(load_css(), unsafe_allow_html=True)


# ============================================================
# CONSTANTS
# ============================================================

EXECUTIVE_SUMMARY_QUESTION = (
    "Generate an executive summary explaining the Technical Result movement "
    "from the current quarter compared with the previous quarter."
)


# ============================================================
# FORMATTING
# ============================================================


def format_million(value):
    if value is None:
        return "N/A"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A"

    sign = "-" if value < 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{sign}${absolute / 1_000_000_000:,.2f}B"
    if absolute >= 1_000_000:
        return f"{sign}${absolute / 1_000_000:,.2f}M"
    if absolute >= 1_000:
        return f"{sign}${absolute / 1_000:,.2f}K"
    return f"{sign}${absolute:,.2f}"


def format_change(value):
    if value is None:
        return "N/A"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "N/A"

    sign = "+" if value > 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{sign if value >= 0 else '-'}${absolute / 1_000_000_000:,.2f}B"
    if absolute >= 1_000_000:
        return f"{sign if value >= 0 else '-'}${absolute / 1_000_000:,.2f}M"
    if absolute >= 1_000:
        return f"{sign if value >= 0 else '-'}${absolute / 1_000:,.2f}K"
    return f"{sign}${absolute:,.2f}" if value >= 0 else f"-${absolute:,.2f}"


def investigation_title(number, level):
    if level == "Quarter":
        if st.session_state.get("period_mode") == "custom":
            title = "Period Comparison"
        else:
            title = "Quarter Comparison"
    else:
        title = {
            "Main_Line_of_Business": "Main Line of Business Drivers",
            "UW_Portfolio": "UW Portfolio Drivers",
            "Cedent_Name": "Cedent Drivers",
            "Renewal_Category": "Renewal / New Business / Cancelled",
        }.get(level, level or "Investigation")
    return f"Investigation {number} — {title}"


def display_commentary(text):
    """Render commentary as escaped plain text so Markdown/LaTeX cannot distort it."""
    if not text:
        st.warning("No executive commentary was generated.")
        return

    safe = html.escape(str(text)).replace("\n\n", "</p><p>").replace("\n", "<br>")
    st.markdown(
        f"""
        <div style="
            background:#ffffff;
            border:1px solid #d9e2ec;
            border-radius:12px;
            padding:22px 24px;
            line-height:1.75;
            font-size:16px;
            color:#243b53;
            margin-top:8px;
        ">
            <p style="margin-top:0;">{safe}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# SESSION STATE
# ============================================================

defaults = {
    "analysis_started": False,
    "region": None,
    "market_unit": None,
    "dashboard": None,
    "analysis_response": None,
    "chat_open": False,
    "chat_messages": [],
    "investigation_states": {},
    "analysis_period": None,
    "analysis_running": False,
    "period_mode": None,
    "custom_open": False,
    "custom_from_date": None,
    "custom_to_date": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# FILTERS
# ============================================================

loader = FilterLoader()
regions = loader.get_regions()

if not regions:
    st.error("No regions found in the database.")
    loader.close()
    st.stop()

selected_region = (
    st.session_state.region if st.session_state.region in regions else regions[0]
)
market_units = loader.get_market_units(selected_region)

if not market_units:
    st.error(f"No market units found for {selected_region}.")
    loader.close()
    st.stop()

selected_market = (
    st.session_state.market_unit
    if st.session_state.market_unit in market_units
    else market_units[0]
)
loader.close()


# ============================================================
# HOME SCREEN
# ============================================================

if not st.session_state.analysis_started:
    col1, col2, col3 = st.columns([1.0, 2.5, 1.0])

    with col2:
        st.markdown(
            """
            <div style="
                text-align:center;
                padding:42px 30px;
                background:white;
                border-radius:18px;
                box-shadow:0 8px 30px rgba(0,0,0,0.08);
                margin-bottom:25px;
            ">
                <div style="font-size:42px;font-weight:700;color:#102A43;margin-bottom:12px;">
                    AI Financial Analyst
                </div>
                Transform P&amp;C Finance data into Executive Insights using AI
            </div>
            """,
            unsafe_allow_html=True,
        )

        region = st.selectbox("Region", regions, index=regions.index(selected_region))

        filter_loader = FilterLoader()
        available_market_units = filter_loader.get_market_units(region)
        filter_loader.close()

        market = st.selectbox("Market Unit", available_market_units)

        st.write("")
        if st.button("🚀 Start Analysis", use_container_width=True):
            engine = AnalysisEngine()
            dashboard = engine.get_dashboard(region, market)
            engine.close()

            if dashboard is None:
                st.error("No dashboard data is available for the selected market.")
                st.stop()

            st.session_state.region = region
            st.session_state.market_unit = market
            st.session_state.dashboard = dashboard
            st.session_state.analysis_response = None
            st.session_state.chat_open = False
            st.session_state.chat_messages = []
            st.session_state.investigation_states = {}
            st.session_state.analysis_period = None
            st.session_state.analysis_running = False
            st.session_state.period_mode = None
            st.session_state.custom_open = False
            st.session_state.custom_from_date = None
            st.session_state.custom_to_date = None
            st.session_state.analysis_started = True
            st.rerun()


# ============================================================
# MAIN DASHBOARD
# ============================================================

else:
    dashboard = st.session_state.dashboard

    st.title("📊 AI Financial Analyst")
    st.caption(
        f"Region: **{st.session_state.region}** | "
        f"Market Unit: **{st.session_state.market_unit}**"
    )
    st.divider()

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Actual TR", format_million(dashboard["Actual_TR"]))
    with c2:
        st.metric("Actual Premium", format_million(dashboard["Actual_Premium"]))
    with c3:
        st.metric("NB Expected TR", format_million(dashboard["NB_Expected_TR"]))
    with c4:
        st.metric("NB Expected Premium", format_million(dashboard["NB_Expected_Premium"]))
    with c5:
        st.metric("TCR", f"{dashboard['TCR'] * 100:.1f}%")

    st.divider()

    left, right = st.columns([2.5, 1])

    with left:
        st.subheader("Executive Commentary")
        commentary_placeholder = st.empty()

        if st.session_state.analysis_response:
            previous_commentary = st.session_state.analysis_response.get("commentary")
            if previous_commentary:
                with commentary_placeholder:
                    display_commentary(previous_commentary)

    with right:

        st.markdown("### Generate Summary")

        st.caption(
            "The AI Analyst compares the current and previous quarter, "
            "selects material drivers using an 80% contribution rule, "
            "and progressively drills into the business hierarchy."
        )

        st.info(
            "SQL runs in the backend and is retained in the application logs. "
            "The user interface shows only the analytical questions, result "
            "tables and selected drivers."
        )

        generate = False

        if st.button(
            "🚀 Generate Executive Summary for the quarter",
            key="generate_quarter_button",
            use_container_width=True
        ):
            generate = True
            st.session_state.period_mode = "quarter"
            st.session_state.custom_open = False

        st.write("")

        if st.button(
            "🗓️ Generate Executive Summary for specific dates",
            key="toggle_custom_date_button",
            use_container_width=True
        ):
            st.session_state.custom_open = not st.session_state.custom_open
            st.rerun()

        if st.session_state.custom_open:

            with st.container(border=True):

                today = date.today()
                default_start = date(
                    today.year,
                    ((today.month - 1) // 3) * 3 + 1,
                    1
                )

                st.markdown("**Select the period to analyse**")
                st.caption(
                    "The analyst filters the data to your selected window "
                    "and compares it with the immediately preceding period "
                    "before running the drill-down."
                )

                date_col1, date_col2 = st.columns(2)

                with date_col1:
                    custom_from = st.date_input(
                        "From",
                        value=default_start,
                        key="custom_from_date"
                    )

                with date_col2:
                    custom_to = st.date_input(
                        "To",
                        value=today,
                        key="custom_to_date"
                    )

                if st.button(
                    "🚀 Generate for this period",
                    key="generate_custom_button",
                    use_container_width=True
                ):
                    generate = True
                    st.session_state.period_mode = "custom"

        st.write("")

        # ========================================================
        # DATA ASSISTANT — FIXED RIGHT-HAND CHAT BOX
        # ========================================================
        #
        # The assistant is deliberately kept INSIDE the right column.
        # It has a fixed height, so a long conversation scrolls inside
        # the box instead of expanding the page.
        #
        # The investigation trail remains below the dashboard and is
        # persisted in st.session_state, so opening/closing the assistant
        # does not make the drill-down evidence disappear.
        # ========================================================

        if not st.session_state.chat_open:

            if st.button(
                "💬 Data Assistant",
                use_container_width=True
            ):
                st.session_state.chat_open = True
                st.rerun()

        else:

            # Fixed-size assistant panel.
            with st.container(
                height=680,
                border=True
            ):

                top_left, top_right = st.columns([4, 1])

                with top_left:
                    st.markdown("### 💬 Data Assistant")

                with top_right:

                    if st.button(
                        "✖ Close",
                        key="close_data_assistant",
                        use_container_width=True
                    ):
                        st.session_state.chat_open = False
                        st.rerun()

                st.caption(
                    f"Ask about **{st.session_state.market_unit}** "
                    f"in **{st.session_state.region}** only."
                )

                st.markdown(
                    """
                    <div style="
                        padding:10px 12px;
                        border-radius:8px;
                        background:#f4f7fb;
                        border:1px solid #d9e2ec;
                        font-size:13px;
                        margin-bottom:10px;
                    ">
                        The assistant converts your question to SQL,
                        queries the selected market, and answers using
                        the returned financial data.
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                with st.expander(
                    "💡 Sample questions",
                    expanded=False
                ):

                    st.write(
                        "How was this market in 2025 Q2?"
                    )
                    st.write(
                        "Did Technical Result improve or decline in 2026 Q3?"
                    )
                    st.write(
                        "Which MLOB had the highest Technical Result "
                        "in 2026 Q3?"
                    )
                    st.write(
                        "How much premium was generated from New Business?"
                    )
                    st.write(
                        "Which businesses were cancelled in 2026 Q3?"
                    )
                    st.write(
                        "What were the claims in 2025 Q2?"
                    )
                    st.write(
                        "Which cedent had the largest Technical Result?"
                    )

                # ------------------------------------------------
                # SCROLLABLE CHAT HISTORY
                # ------------------------------------------------

                chat_history = st.container(
                    height=380,
                    border=True
                )

                with chat_history:

                    if not st.session_state.chat_messages:

                        st.info(
                            "Ask me anything about the financial data "
                            "for this selected market."
                        )

                    for message in st.session_state.chat_messages:

                        role = message.get("role")
                        content = message.get("content", "")

                        if role == "user":
                            st.markdown("**You**")
                        else:
                            st.markdown("**🤖 Data Assistant**")

                        # Use plain text so Markdown/LaTeX from the model
                        # cannot make financial values look broken.
                        st.write(content)

                        if message.get("data") is not None:

                            with st.expander(
                                f"Supporting data "
                                f"({message.get('rows', 0)} rows)",
                                expanded=False
                            ):

                                st.dataframe(
                                    message["data"],
                                    use_container_width=True,
                                    hide_index=True
                                )

                # ------------------------------------------------
                # INPUT
                # ------------------------------------------------

                chat_question = st.text_input(
                    "Ask a question",
                    placeholder=(
                        "e.g. Was 2026 Q3 a good quarter for this market?"
                    ),
                    key="chat_question_input"
                )

                ask_chat = st.button(
                    "Send",
                    key="send_chat_question",
                    use_container_width=True
                )

                if ask_chat:

                    if not chat_question.strip():

                        st.warning(
                            "Please enter a question."
                        )

                    else:

                        question_text = chat_question.strip()

                        st.session_state.chat_messages.append(
                            {
                                "role": "user",
                                "content": question_text
                            }
                        )

                        with st.spinner(
                            "Analyst is querying the financial data..."
                        ):

                            try:

                                chatbot = DataChatbot()

                                chat_response = chatbot.ask(
                                    question=question_text,
                                    region=st.session_state.region,
                                    market_unit=st.session_state.market_unit
                                )

                            except Exception as exc:

                                chat_response = {
                                    "success": False,
                                    "message": str(exc)
                                }

                        if chat_response.get("success"):

                            st.session_state.chat_messages.append(
                                {
                                    "role": "assistant",
                                    "content": chat_response.get(
                                        "answer",
                                        "No answer was generated."
                                    ),
                                    "data": chat_response.get(
                                        "data"
                                    ),
                                    "rows": chat_response.get(
                                        "row_count",
                                        0
                                    )
                                }
                            )

                        else:

                            st.session_state.chat_messages.append(
                                {
                                    "role": "assistant",
                                    "content": (
                                        "I could not complete that query: "
                                        + chat_response.get(
                                            "message",
                                            "Unknown error."
                                        )
                                    )
                                }
                            )

                        st.rerun()

    # --------------------------------------------------------
    # RESTORE INVESTIGATION TRAIL AFTER A STREAMLIT RERUN
    # --------------------------------------------------------
    #
    # Opening the chatbot causes a Streamlit rerun. The investigation
    # data is now stored in session_state, so the completed drill-down
    # remains visible underneath/behind the overlay.
    # --------------------------------------------------------

    if (
        not generate
        and st.session_state.analysis_response
        and st.session_state.investigation_states
    ):

        st.subheader("🔎 Analyst Investigation")

        if st.session_state.analysis_period:
            st.caption(
                f"Analysis period: **{st.session_state.analysis_period}**"
            )

        restored_area = st.container()

        for number in sorted(
            st.session_state.investigation_states.keys()
        ):

            state = st.session_state.investigation_states[number]

            level = state.get("level", "")
            dataframe = state.get("data")
            drivers = state.get("drivers", [])
            coverage = state.get("coverage")
            focus_dimension = state.get("focus_dimension")
            focus_value = state.get("focus_value")
            status = state.get("status", "")
            execution_time = state.get("execution_time", 0)
            question = state.get("question")

            with restored_area:

                with st.expander(
                    investigation_title(number, level),
                    expanded=False
                ):

                    if focus_dimension and focus_value:
                        st.info(
                            f"🎯 Context: "
                            f"**{focus_dimension} = {focus_value}**"
                        )

                    if question:
                        st.markdown("**Analytical Question**")
                        st.write(question)

                    if status == "completed":
                        st.success("✅ Investigation completed.")

                    elif status == "error":
                        st.error(
                            state.get(
                                "error",
                                "Investigation failed."
                            )
                        )

                    if dataframe is not None:

                        st.markdown("**Result**")

                        st.dataframe(
                            dataframe,
                            use_container_width=True,
                            hide_index=True
                        )

                        st.caption(
                            f"Rows returned: {len(dataframe)} | "
                            f"Execution time: {execution_time:.3f}s"
                        )

                    if drivers:

                        st.markdown(
                            "**Material drivers selected**"
                        )

                        driver_rows = []

                        for i, item in enumerate(
                            drivers,
                            start=1
                        ):

                            driver_rows.append(
                                {
                                    "Rank": i,
                                    "Driver": item.get("driver"),
                                    "TR Change": format_change(
                                        item.get("change")
                                    ),
                                    "Direction": item.get(
                                        "direction",
                                        ""
                                    ).title(),
                                }
                            )

                        st.dataframe(
                            driver_rows,
                            use_container_width=True,
                            hide_index=True
                        )

                        if (
                            coverage is not None
                            and level != "Renewal_Category"
                        ):

                            st.caption(
                                f"Coverage: "
                                f"{coverage * 100:.1f}% of the parent "
                                f"Technical Result movement "
                                f"(target: 80%; minimum 3 contributors "
                                f"when available)."
                            )

                    elif (
                        level == "Renewal_Category"
                        and dataframe is not None
                    ):

                        st.caption(
                            "All available Renewal, New Business and "
                            "Cancelled categories are retained for "
                            "interpretation."
                        )

    st.divider()

    if generate:

        st.session_state.analysis_response = None
        st.session_state.investigation_states = {}
        st.session_state.analysis_period = None
        st.session_state.analysis_running = True

        commentary_placeholder.empty()

        # ------------------------------------------------
        # Period resolution
        # ------------------------------------------------
        # quarter -> default auto current/previous quarter
        # custom  -> user-selected dates, previous period derived
        period = None

        if st.session_state.period_mode == "custom":

            custom_from = st.session_state.get("custom_from_date")
            custom_to = st.session_state.get("custom_to_date")

            if custom_from is None or custom_to is None:
                st.error("Please select both the From and To dates.")
                st.stop()

            if custom_from > custom_to:
                st.error("The 'From' date must not be after the 'To' date.")
                st.stop()

            try:
                period = build_date_period(custom_from, custom_to)
            except ValueError as exc:
                st.error(str(exc))
                st.stop()

        st.subheader("🔎 Analyst Investigation")
        st.caption(
            "The analyst shows the financial result and material drivers at each level. "
            "Only the information useful to a business user is displayed."
        )

        investigation_area = st.container()

        # Keep the investigation trail in session state.
        # Streamlit reruns the script whenever a widget is clicked.
        # Without this, opening the chatbot would erase the locally
        # stored investigation states from the previous run.
        investigation_states = st.session_state.investigation_states

        def render_investigation(number):
            if number not in investigation_states:
                return

            state = investigation_states[number]
            level = state.get("level", "")
            dataframe = state.get("data")
            drivers = state.get("drivers", [])
            coverage = state.get("coverage")
            focus_dimension = state.get("focus_dimension")
            focus_value = state.get("focus_value")
            status = state.get("status", "")
            execution_time = state.get("execution_time", 0)
            question = state.get("question")

            placeholder = state.get("placeholder")
            if placeholder is None:
                placeholder = investigation_area.empty()
                state["placeholder"] = placeholder

            with placeholder.container():
                with st.expander(investigation_title(number, level), expanded=True):
                    if focus_dimension and focus_value:
                        st.info(f"🎯 Context: **{focus_dimension} = {focus_value}**")

                    if question:
                        st.markdown("**Analytical Question**")
                        st.write(question)

                    if status == "starting":
                        st.info("🤖 Preparing investigation...")
                    elif status == "generating":
                        st.info("🤖 Preparing financial analysis...")
                    elif status == "executing":
                        st.info("⚙️ Running analysis against the financial database...")
                    elif status == "completed":
                        st.success("✅ Investigation completed.")
                    elif status == "error":
                        st.error(state.get("error", "Investigation failed."))

                    if dataframe is not None:
                        st.markdown("**Result**")
                        st.dataframe(dataframe, use_container_width=True, hide_index=True)
                        st.caption(
                            f"Rows returned: {len(dataframe)} | Execution time: {execution_time:.3f}s"
                        )

                    if drivers:
                        st.markdown("**Material drivers selected**")
                        driver_rows = []
                        for i, item in enumerate(drivers, start=1):
                            driver_rows.append(
                                {
                                    "Rank": i,
                                    "Driver": item.get("driver"),
                                    "TR Change": format_change(item.get("change")),
                                    "Direction": item.get("direction", "").title(),
                                }
                            )
                        st.dataframe(driver_rows, use_container_width=True, hide_index=True)

                        if coverage is not None and level != "Renewal_Category":
                            st.caption(
                                f"Coverage: {coverage * 100:.1f}% of the parent Technical Result movement "
                                f"(target: 80%; minimum 3 contributors when available)."
                            )
                    elif level == "Renewal_Category" and dataframe is not None:
                        st.caption(
                            "All available Renewal, New Business and Cancelled categories are retained for interpretation."
                        )

        def progress_callback(event):
            if not event:
                return

            event_type = event.get("type")

            if event_type == "period":

                label = event.get("label")
                if not label:
                    label = (
                        f"{event.get('current_year')} Q{event.get('current_quarter')}"
                        f" vs "
                        f"{event.get('previous_year')} Q{event.get('previous_quarter')}"
                    )

                st.session_state.analysis_period = label

                with investigation_area:
                    st.info(
                        f"📅 Analysis period: "
                        f"**{label}**"
                    )

            elif event_type == "investigation_start":
                number = event.get("investigation")
                investigation_states[number] = {
                    "level": event.get("level"),
                    "question": event.get("question"),
                    "data": None,
                    "drivers": [],
                    "coverage": None,
                    "focus_dimension": event.get("focus_dimension"),
                    "focus_value": event.get("focus_value"),
                    "status": "starting",
                    "execution_time": 0,
                    "placeholder": None,
                }
                render_investigation(number)

            elif event_type == "sql_generating":
                number = event.get("investigation")
                if number in investigation_states:
                    investigation_states[number]["status"] = "generating"
                    render_investigation(number)

            elif event_type == "sql_executed":
                number = event.get("investigation")
                if number in investigation_states:
                    investigation_states[number]["status"] = "executing"
                    investigation_states[number]["execution_time"] = event.get("execution_time", 0)
                    render_investigation(number)

            elif event_type == "result":
                number = event.get("investigation")
                if number in investigation_states:
                    investigation_states[number]["data"] = event.get("data")
                    investigation_states[number]["status"] = "completed"
                    investigation_states[number]["execution_time"] = event.get("execution_time", 0)
                    investigation_states[number]["focus_dimension"] = event.get("focus_dimension")
                    investigation_states[number]["focus_value"] = event.get("focus_value")
                    render_investigation(number)

            elif event_type == "overall_movement":
                with investigation_area:
                    change = event.get("change")
                    direction = event.get("direction")
                    if direction == "negative":
                        st.warning(f"📉 Technical Result deteriorated by **{format_change(change)}**.")
                    elif direction == "positive":
                        st.success(f"📈 Technical Result improved by **{format_change(change)}**.")
                    else:
                        st.info("Technical Result remained broadly unchanged.")

            elif event_type == "driver_selected":
                number = event.get("investigation")
                if number not in investigation_states:
                    return
                investigation_states[number]["drivers"] = event.get("drivers", [])
                investigation_states[number]["coverage"] = event.get("coverage")
                investigation_states[number]["parent_value"] = event.get("parent_value")
                render_investigation(number)

            elif event_type == "commentary_generating":
                with investigation_area:
                    st.markdown("---")
                    st.info("🧠 All material drivers collected. Generating executive commentary...")

            elif event_type == "commentary_ready":
                commentary = event.get("commentary")
                if commentary:
                    with commentary_placeholder:
                        display_commentary(commentary)

            elif event_type == "error":
                number = event.get("investigation")
                message = event.get("message", "Unknown analyst error.")
                if number in investigation_states:
                    investigation_states[number]["status"] = "error"
                    investigation_states[number]["error"] = message
                    render_investigation(number)
                else:
                    with investigation_area:
                        st.error(message)

        try:
            if period is None:
                summary_question = EXECUTIVE_SUMMARY_QUESTION
            else:
                summary_question = (
                    "Generate an executive summary explaining the Technical Result movement "
                    f"from {period['current_start']} to {period['current_end']} "
                    "compared with the immediately preceding period."
                )

            orchestrator = AnalystOrchestrator()
            response = orchestrator.analyze(
                question=summary_question,
                region=st.session_state.region,
                market_unit=st.session_state.market_unit,
                period=period,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            st.error(f"Analysis failed: {exc}")
            st.stop()

        st.session_state.analysis_response = response
        st.session_state.analysis_running = False

        if response.get("success"):
            st.success(
                f"✅ Analyst completed {response.get('investigations', 0)} financial investigations."
            )

            st.markdown("---")
            st.markdown("### 📌 Investigation Summary")
            summary_col1, summary_col2, summary_col3 = st.columns(3)
            with summary_col1:
                st.metric("Analysis Period", response.get("period", "N/A"))
            with summary_col2:
                st.metric("TR Change", format_change(response.get("overall_change")))
            with summary_col3:
                st.metric("Investigations", response.get("investigations", 0))
        else:
            st.error(response.get("message", "The analyst could not complete the analysis."))