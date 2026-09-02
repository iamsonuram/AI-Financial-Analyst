def load_css():
    return """
    <style>

    /* ============ BASE ============ */
    .stApp{
        background:#F6F8FB;
        color:#0F2233;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    html, body, [class*="css"]{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }

    #MainMenu, footer, header[data-testid="stHeader"]{
        visibility: hidden;
        height: 0;
    }

    /* Hide the default Streamlit sidebar affordance / keep it collapsed */
    section[data-testid="stSidebar"]{
        display: none;
    }

    .block-container{
        padding-top: 1.5rem;
        padding-bottom: 3rem;
        max-width: 1220px;
    }

    h1, h2, h3{
        color:#0F2B46;
        letter-spacing:-0.01em;
    }

    /* ============ APP HEADER ============ */
    .app-header{
        padding: 26px 30px;
        background: linear-gradient(135deg, #0F2B46 0%, #16405F 100%);
        border-radius: 16px;
        margin-bottom: 22px;
        color:#ffffff;
        border:1px solid #0B2238;
    }
    .app-header .app-title{
        font-size: 30px;
        font-weight: 700;
        margin:0;
        color:#ffffff;
        letter-spacing:-0.01em;
    }
    .app-header .app-context{
        margin-top: 8px;
        font-size: 14px;
        color:#BFD3E6;
    }
    .app-header .app-context b{
        color:#ffffff;
    }

    /* ============ TOP NAV TABS ============ */
    .topnav{
        display:flex;
        gap:6px;
        background:#ffffff;
        border:1px solid #E2E8F0;
        border-radius:12px;
        padding:6px;
        margin-bottom:24px;
        box-shadow:0 1px 2px rgba(15,42,70,.04);
        flex-wrap:wrap;
        align-items:center;
    }
    .topnav .tn-tab{
        display:inline-block;
        border:none;
        background:transparent;
        color:#486581;
        font-size:14px;
        font-weight:600;
        padding:9px 16px;
        border-radius:8px;
        cursor:pointer;
        font-family:inherit;
        text-decoration:none;
        transition:all .15s ease;
        text-align:center;
        flex:0 0 auto;
    }
    .topnav .tn-tab:hover{
        background:#F0F4F9;
        color:#0F2B46;
        text-decoration:none;
    }
    .topnav .tn-tab.active{
        background:#0F2B46;
        color:#ffffff;
        box-shadow:0 1px 2px rgba(15,42,70,.25);
    }
    @media (max-width: 700px){
        .topnav{ flex-wrap:wrap; }
        .topnav .tn-tab{ flex:1 1 auto; text-align:center; }
    }

    /* In-app Streamlit-button navigation (keeps the pill look) */
    .topnav > [data-testid="stVerticalBlock"] > [data-testid="stColumn"]{
        padding: 0;
    }
    .topnav [data-testid="stButton"]{
        width: 100%;
    }
    .topnav [data-testid="stButton"] > button{
        border:none;
        background:transparent;
        color:#486581;
        font-size:14px;
        font-weight:600;
        padding:9px 16px;
        border-radius:8px;
        cursor:pointer;
        width:100%;
        text-align:center;
        white-space:nowrap;
        transition:all .15s ease;
        box-shadow:none;
    }
    .topnav [data-testid="stButton"] > button:hover{
        background:#F0F4F9;
        color:#0F2B46;
        border:none;
    }
    .topnav [data-testid="stButton"] > button[kind="primary"]{
        background:#0F2B46;
        color:#ffffff;
        box-shadow:0 1px 2px rgba(15,42,70,.25);
    }
    .topnav [data-testid="stButton"] > button[kind="primary"]:hover{
        background:#16405F;
        color:#ffffff;
    }
    .topnav [data-testid="stButton"] > button[kind="secondary"]{
        background:transparent;
        color:#486581;
    }
    .topnav [data-testid="stButton"] > button[kind="secondary"]:hover{
        background:#F0F4F9;
        color:#0F2B46;
    }
    @media (max-width: 700px){
        .topnav [data-testid="stColumn"]{ flex:1 1 auto; }
    }

    /* ============ CARDS ============ */
    .card{
        background:#ffffff;
        border:1px solid #E2E8F0;
        border-radius:14px;
        padding:20px 22px;
        margin-bottom:18px;
        box-shadow:0 1px 3px rgba(15,42,70,.05);
    }
    .card-title{
        font-size:15px;
        font-weight:700;
        color:#0F2B46;
        margin-bottom:4px;
    }
    .card-sub{
        font-size:12.5px;
        color:#677F99;
        margin-bottom:12px;
    }

    /* ============ PERIOD HEADER ============ */
    .period-card{
        background:#F7FAFD;
        border:1px solid #E2E8F0;
        border-left:4px solid #0F2B46;
        border-radius:10px;
        padding:12px 16px;
        margin-bottom:8px;
    }
    .period-row{
        line-height:1.8;
    }

    /* ============ KPI CARDS ============ */
    .kpi-grid{
        display:grid;
        grid-template-columns:repeat(5,1fr);
        gap:14px;
        margin-bottom:22px;
    }
    .kpi-card{
        background:#ffffff;
        border:1px solid #E2E8F0;
        border-radius:14px;
        padding:18px 18px 16px;
        box-shadow:0 1px 3px rgba(15,42,70,.05);
    }
    .kpi-card .kpi-label{
        font-size:12px;
        font-weight:600;
        color:#677F99;
        text-transform:uppercase;
        letter-spacing:.04em;
        margin-bottom:8px;
    }
    .kpi-card .kpi-value{
        font-size:22px;
        font-weight:700;
        color:#0F2B46;
        line-height:1.1;
        margin-bottom:8px;
    }
    .kpi-card .kpi-delta{
        font-size:12.5px;
        font-weight:600;
        padding:3px 8px;
        border-radius:20px;
        display:inline-block;
    }
    .kpi-delta.up{ color:#0E7A45; background:#E7F5EC; }
    .kpi-delta.down{ color:#B93A2B; background:#FCEBE8; }
    .kpi-delta.flat{ color:#486581; background:#EEF2F6; }

    /* ============ EXECUTIVE COMMENTARY ============ */
    .comment-title{
        font-size:18px;
        font-weight:700;
        color:#0F2B46;
        margin-bottom:14px;
        border-left:4px solid #0F2B46;
        padding-left:12px;
    }
    .comment-body{
        background:#ffffff;
        border:1px solid #E2E8F0;
        border-left:4px solid #2E6DB4;
        border-radius:12px;
        padding:22px 24px;
        line-height:1.75;
        font-size:15px;
        color:#243B53;
    }
    .comment-body p{
        margin:0 0 12px;
    }
    .comment-body p:last-child{
        margin-bottom:0;
    }

    /* ============ TAKEAWAYS ============ */
    .takeaway{
        display:flex;
        align-items:flex-start;
        gap:10px;
        padding:10px 14px;
        border-radius:10px;
        background:#F7FAFD;
        border:1px solid #E6EEF6;
        margin-bottom:8px;
        font-size:14px;
        color:#243B53;
    }
    .takeaway .tick{
        color:#0E7A45;
        font-weight:700;
        flex-shrink:0;
    }

    /* ============ DRIVER PILLS ============ */
    .driver-row{
        display:flex;
        align-items:center;
        gap:12px;
        margin-bottom:8px;
    }
    .driver-name{
        width:200px;
        font-size:13px;
        font-weight:600;
        color:#243B53;
        text-align:right;
    }
    .driver-bar{
        flex:1;
        height:16px;
        border-radius:6px;
        background:#EEF2F6;
        overflow:hidden;
    }
    .driver-bar > div{
        height:100%;
        border-radius:6px;
    }
    .driver-bar.pos > div{ background:#2F9E63; }
    .driver-bar.neg > div{ background:#D9534F; }
    .driver-val{
        width:110px;
        font-size:12.5px;
        font-weight:600;
        color:#243B53;
    }

    /* ============ STRIPED SECTION TITLE ============ */
    .section-head{
        display:flex;
        align-items:center;
        gap:10px;
        margin:6px 0 14px;
    }
    .section-head .bar{
        width:4px;
        height:18px;
        border-radius:2px;
        background:#2E6DB4;
    }
    .section-head .txt{
        font-size:16px;
        font-weight:700;
        color:#0F2B46;
    }

    /* ============ DIVIDERS / SPACING ============ */
    .rule{
        height:1px;
        background:#E2E8F0;
        margin:22px 0;
    }

    /* ============ UTIL ============ */
    .muted{
        color:#677F99;
    }
    .small{
        font-size:12.5px;
    }
    .center{
        text-align:center;
    }

    /* ============ STREAMLIT OVERRIDES ============ */
    .stButton > button{
        border-radius:9px;
        font-weight:600;
        border:1px solid #D3DEE9;
        background:#ffffff;
        color:#0F2B46;
        transition:all .15s ease;
    }
    .stButton > button:hover{
        border-color:#0F2B46;
        background:#F0F4F9;
    }
    .stButton > button[kind="primary"]{
        background:#0F2B46;
        border-color:#0F2B46;
        color:#ffffff;
    }
    .stButton > button[kind="primary"]:hover{
        background:#16405F;
        border-color:#16405F;
    }
    div[data-testid="stMetric"]{
        background:#ffffff;
        border:1px solid #E2E8F0;
        border-radius:14px;
        padding:14px 16px;
    }
    div[data-testid="stExpander"]{
        border:1px solid #E2E8F0;
        border-radius:12px;
        background:#ffffff;
        overflow:hidden;
        margin-bottom:10px;
    }
    div[data-testid="stExpander"] summary{
        font-weight:600;
        color:#0F2B46;
    }
    /* Subtle chart cards via the visual card class */
    .viz-card{
        background:#ffffff;
        border:1px solid #E2E8F0;
        border-radius:14px;
        padding:8px 6px 4px;
        box-shadow:0 1px 3px rgba(15,42,70,.05);
    }

    @media (max-width: 900px){
        .kpi-grid{ grid-template-columns:repeat(2,1fr); }
    }
    @media (max-width: 560px){
        .kpi-grid{ grid-template-columns:1fr; }
        .driver-name{ width:120px; }
    }

    </style>
    """
