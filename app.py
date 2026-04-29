import streamlit as st
import os
import io
import time
import pydub
import google.generativeai as genai
# from deepgram import DeepgramClient, PrerecordedOptions  # SDK 대신 requests 직접 호출 사용
import pyperclip
import shutil
import requests
import streamlit.components.v1 as components
import sys

# --- Environment Setup (Windows Encoding Fix) ---
if sys.stdout and sys.stdout.encoding != 'utf-8':
    try: sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except: pass
if sys.stderr and sys.stderr.encoding != 'utf-8':
    try: sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except: pass


# --- Supabase Configuration (REST API Mode) ---
SUPABASE_URL = "https://iqtggenzwnzltbwfqqdf.supabase.co/rest/v1"
SUPABASE_KEY = "sb_publishable_8aeTO3X-R0ZeMTS26tDOzA_81ILuvYE"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# --- Constants & Configuration ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDS_DIR = os.path.join(APP_DIR, "records")
AUDIO_DIR = os.path.join(RECORDS_DIR, "audio")
CLINIC_CHARTS_DIR = os.path.join(RECORDS_DIR, "charts")

# Ensure directories exist
try:
    os.makedirs(AUDIO_DIR, exist_ok=True)
    os.makedirs(CLINIC_CHARTS_DIR, exist_ok=True)
except Exception as e:
    st.warning(f"폴더 생성 권한 오류: {e}")

MARIO_LOGO_FILENAME = "cute_mario_face_icon_1776402340674.png"
MARIO_LOGO = os.path.join(APP_DIR, MARIO_LOGO_FILENAME)

# --- FFmpeg Setup ---
if shutil.which("ffmpeg"):
    pydub.AudioSegment.converter = "ffmpeg"
else:
    ffmpeg_local_path = r"C:\Users\WD\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.WinGet.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin"
    if os.path.exists(ffmpeg_local_path):
        os.environ["PATH"] += os.pathsep + ffmpeg_local_path
        pydub.AudioSegment.converter = os.path.join(ffmpeg_local_path, "ffmpeg.exe")

st.set_page_config(page_title="Mario Scribe 2.0", page_icon=MARIO_LOGO if os.path.exists(MARIO_LOGO) else None, layout="wide")

# --- Helper Functions ---
def get_api_key(key_name, filename):
    try:
        if key_name in st.secrets: 
            return st.secrets[key_name]
    except Exception:
        pass
    
    env_val = os.environ.get(key_name)
    if env_val: return env_val
    
    path = os.path.join(APP_DIR, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f: return f.read().strip()
        except: pass
    return ""


def save_key(filename, key):
    try:
        with open(os.path.join(APP_DIR, filename), "w", encoding="utf-8") as f:
            f.write(key)
    except: pass

def load_user_profile(user_id):
    """REST API를 사용해 DB에서 사용자의 맞춤 프롬프트를 불러옵니다."""
    try:
        url = f"{SUPABASE_URL}/profiles?user_id=eq.{user_id}&select=custom_prompt"
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200 and response.json():
            return response.json()[0].get("custom_prompt")
    except Exception as e:
        st.error(f"프로필 로드 실패: {e}")
    return None

def save_user_profile(user_id, prompt):
    """REST API를 사용해 DB에 사용자의 맞춤 프롬프트를 저장합니다 (Upsert)."""
    try:
        url = f"{SUPABASE_URL}/profiles"
        data = {"user_id": user_id, "custom_prompt": prompt}
        # Upsert headers
        upsert_headers = HEADERS.copy()
        upsert_headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
        
        response = requests.post(url, headers=upsert_headers, json=data)
        if response.status_code in [200, 201, 204]:
            st.success("DB에 설정이 안전하게 저장되었습니다!")
        else:
            st.error(f"DB 저장 실패 ({response.status_code}): {response.text}")
    except Exception as e:
        st.error(f"DB 연결 실패: {e}")

def save_chart_log(user_id, transcription, chart):
    """REST API를 사용해 chart_logs 테이블에 기록을 저장합니다."""
    try:
        url = f"{SUPABASE_URL}/chart_logs"
        data = {"user_id": user_id, "transcription": transcription, "chart": chart}
        response = requests.post(url, headers=HEADERS, json=data)
        if response.status_code not in [200, 201, 204]:
            st.error(f"차트 로그 저장 실패: {response.text}")
    except Exception as e:
        st.warning(f"차트 로그 서버 연결 오류: {e}")

def fetch_chart_logs(limit=50):
    """REST API를 사용해 최근 chart_logs를 가져옵니다."""
    try:
        url = f"{SUPABASE_URL}/chart_logs?select=*&order=created_at.desc&limit={limit}"
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.error(f"로그 조회 실패: {e}")
    return []

# Initialize session state
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def authenticate_user(email, password):
    url = f"https://iqtggenzwnzltbwfqqdf.supabase.co/auth/v1/token?grant_type=password"
    data = {"email": email, "password": password}
    response = requests.post(url, headers={"apikey": SUPABASE_KEY}, json=data)
    if response.status_code == 200:
        return True, response.json()
    return False, response.json().get("error_description", "로그인 실패")

def register_user(email, password):
    url = f"https://iqtggenzwnzltbwfqqdf.supabase.co/auth/v1/signup"
    data = {"email": email, "password": password}
    response = requests.post(url, headers={"apikey": SUPABASE_KEY}, json=data)
    if response.status_code == 200:
        return True, "회원가입 성공! 이제 로그인해 주세요."
    return False, response.json().get("msg", "회원가입 실패")

def login():
    st.markdown("""
        <div style='text-align: center; padding: 50px;'>
            <h1 style='color: #FF2400;'>Mario Scribe 2.0</h1>
            <p>SaaS 모드: 클라우드 인증 시스템</p>
        </div>
    """, unsafe_allow_html=True)
    
    with st.container():
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            tab1, tab2 = st.tabs(["🔐 로그인", "📝 회원가입"])
            
            with tab1:
                with st.form("login_form"):
                    user_email = st.text_input("이메일 주소")
                    user_pw = st.text_input("비밀번호", type="password")
                    submit = st.form_submit_button("로그인")
                    
                    if submit:
                        if user_email == "admin" and user_pw == "mario1234":
                            # 임시 어드민 로직 유지 (비상용)
                            st.session_state.authenticated = True
                            st.session_state.user_id = "admin"
                            saved_prompt = load_user_profile("admin")
                            if saved_prompt: st.session_state.custom_prompt = saved_prompt
                            st.rerun()
                        else:
                            success, result = authenticate_user(user_email, user_pw)
                            if success:
                                st.session_state.authenticated = True
                                st.session_state.user_id = user_email
                                # DB에서 커스텀 프롬프트 로드
                                saved_prompt = load_user_profile(user_email)
                                if saved_prompt:
                                    st.session_state.custom_prompt = saved_prompt
                                st.success("로그인 성공!")
                                st.rerun()
                            else:
                                st.error(f"오류: {result}")
            
            with tab2:
                with st.form("signup_form"):
                    new_email = st.text_input("이메일 주소 (아이디로 사용)")
                    new_pw = st.text_input("비밀번호 (6자리 이상)", type="password")
                    new_pw_confirm = st.text_input("비밀번호 확인", type="password")
                    signup_submit = st.form_submit_button("가입하기")
                    
                    if signup_submit:
                        if new_pw != new_pw_confirm:
                            st.error("비밀번호가 일치하지 않습니다.")
                        elif len(new_pw) < 6:
                            st.error("비밀번호는 6자리 이상이어야 합니다.")
                        else:
                            success, msg = register_user(new_email, new_pw)
                            if success:
                                st.success(msg)
                            else:
                                st.error(f"오류: {msg}")

if not st.session_state.authenticated:
    login()
    st.stop()

# --- Main App Logic (Authenticated) ---

# Initialize session state for app
if "transcription" not in st.session_state: st.session_state.transcription = ""
if "chart" not in st.session_state: st.session_state.chart = ""
if "last_processed" not in st.session_state: st.session_state.last_processed = None
if "widget_key" not in st.session_state: st.session_state.widget_key = 0

# --- API Keys ---
GEMINI_API_KEY = get_api_key("GEMINI_API_KEY", "gemini_api_key.txt")
DEEPGRAM_API_KEY = get_api_key("DEEPGRAM_API_KEY", "deepgram_api_key.txt")

# --- Prompt Construction ---
today_date = st.sidebar.text_input("진료 날짜", value=time.strftime("%Y.%m.%d."))

DEFAULT_PROMPT = f"""당신은 숙련된 한의사를 돕는 전문 의료 서기입니다.
실제 진료 상황이나 구술 내용을 바탕으로 의료 차트를 작성하세요.

[지침]
1. 한국어로 작성하되, 섹션 제목은 '#' 바로 뒤에 공백 없이 적어 진단명을 기입합니다.
   - **[헤더 접두어]** 목(Posterior neck pain)과 허리(Low back pain)는 중앙 척추 라인이므로 헤더에 방향 접두어를 생략합니다. 그 외 어깨 등 사지 관절 부위는 환자의 증상 방향에 따라 **#Rt, #Lt, #Both** 등의 접두어를 붙여 작성하세요. (예: #Rt shoulder pain)
   - 두통(#Headache), 어지럼증(#Dizziness), 오심(#Nausea)은 항상 각각 독립된 섹션으로 작성하되, 반드시 **요통이나 경추통 같은 근골격계 통증 섹션들을 먼저 작성한 후 그 아래에 위치시켜주세요. (통증 섹션이 항상 두통/어지럼증/오심 섹션보다 위에 와야 합니다.)**
3. 각 진단명 하단에는 '부위', '양상', '패턴', '동반증상' 등을 작성하세요.
   - 단, #Dizziness와 #Nausea 섹션은 '양상' 항목만 작성합니다.
4. **[구조적 핵심] o/s와 ROM 결과는 모든 진단 섹션(두통/어지럼증/오심 포함)이 끝난 후 차트의 가장 아랫부분에 통합하여 작성하세요.**
5. '부위' 섹션은 '좌', '우', '좌/우', '요천추' 등 핵심 키워드만 사용하여 최대한 간결하게 작성하세요.
   - 특히 허리 통증의 경우, 좌측이나 우측의 통증이 '동반증상'의 방사통으로 충분히 표현된다면 '부위'에는 **'요천추'** 등 주된 통증 부위만 기입하고 부가적인 부위는 생략하세요.
   - **양측 모두 아픈 경우 '중앙/양측' 대신 '좌/우'를 사용하세요.**
6. '양상' 섹션은 '묵직함', '쑤심', '뻐근함', '알싸함' 등의 한의학 용어를 우선적으로 사용하세요.
7. '패턴' 섹션은 '지속적', '간헐적' 등 추상적인 빈도를 제외하고, **특정 동작 시 통증이 심해지는 양상을 구체적으로 기술하세요.** (괄호 없이 작성합니다.)
   - 예: **고개를 들 때 통증 심해짐**, **허리를 숙일 때 통증 심해짐**
8. '동반증상' 섹션은 각 부위별 체크 템플릿을 사용하되, (좌/우)나 (둔부/하지)와 같이 구분된 항목은 음성에서 확인된 결과에 따라 (+/+), (+/-), (-/+), (-/-)와 같이 각각의 유무를 명확히 표시하세요.
   - 예: 방사통(좌/우)(-/-) / 저림(좌/우)(-/-) / 감각저하(-) / 근력저하(-)
9. o/s(사고 상황) 섹션은 교통사고(TA)의 경우 아래의 상세 형식을 엄격히 따르세요.
   - 형식: o/s - [날짜]. [장소]에서 [상황]한 TA([충돌유형], [본인위치])(환자진술에 근거함)
   - 예: 시청사거리 상무지구 방향 교차로에서 주행 중 옆 차선에서 끼어들면서 추돌한 TA(car+car, 운전석)(환자진술에 근거함)
10. **[핵심] 임상 용어 및 ROM 작성**:
    - **ROM 결과는 반드시 음성 내용에서 명시적으로 확인된 제한 사항만 기입하세요.** 확인되지 않은 동작(굴곡, 회전 등)을 임의로 추가하지 마세요.
    - **ROM 항목에는 순수한 이학적 검사 소견(가동범위 제한 등)만 작성하며, 통증에 대한 내용(예: "및 통증")은 절대 포함하지 마세요.**
    - ROM 제한 사항이 한 부위에 여러 개 있을 경우 슬래시(/)로 나누지 말고, 띄어쓰기로 묶어서 한 번에 간결하게 작성하세요.
    - 제한 사항 앞에는 반드시 'ROM'이라는 단어를 명시하세요. (형식 예시: C-spine: ROM 굴곡신전 좌우회전 제한 / Wrist: ROM 신전 제한)
    - 교통사고 상황 묘사 시 '후방에서 추돌한'에 국한되지 말고, '끼어들면서 추돌한', '정면 충돌한' 등 실제 상황을 정확히 반영하세요.
11. 환자가 '어제', '오늘' 등으로 말하면 {today_date} 기준으로 정확한 날짜를 계산하여 기입하세요.
12. **[어깨 통증 부위 세분화]** 어깨 통증(#Shoulder pain)의 경우 '부위' 섹션은 반드시 **'전면', '측면', '후면', '승모근'** 중 환자의 증상과 가장 일치하는 하나를 선택하여 작성하세요.
13. **[지명 및 용어 보정]** 음성 인식 오류로 보이는 지명이나 단어는 문맥에 맞게 보정하세요. (예: 휘청 사거리 -> 시청사거리)

[출력 형식 예시]
#Posterior neck pain
부위: 좌/우
양상: 뻐근함
패턴: 고개를 들 때 통증 심해짐
동반증상: 방사통(좌/우)(-/-) / 저림(좌/우)(-/-) / 근력저하(-)

#Low back pain
부위: 요천추
양상: 뻐근함 / 찌름
패턴: 허리를 펼 때 통증 심해짐
동반증상: 방사통(둔부/하지)(-/-) / 저림(좌/우)(-/-) / 감각저하(-) / 근력저하(-)

#Both shoulder pain
부위: 승모근
양상: 뻐근함
패턴: 지속적
동반증상: 방사통(좌/우)(-/-) / 저림(좌/우)(-/-)

#Headache
부위: 후두부
양상: 욱신거림
"""

if "custom_prompt" not in st.session_state:
    st.session_state.custom_prompt = DEFAULT_PROMPT

# --- App UI ---
col_icon, col_title = st.columns([1, 8])
with col_icon:
    if os.path.exists(MARIO_LOGO):
        st.image(MARIO_LOGO, width=100)
with col_title:
    st.title("Mario Scribe 2.0")
    st.markdown(f"### **반갑습니다, {st.session_state.get('user_id', 'admin')} 원장님!**")

# Sidebar
with st.sidebar:
    st.image(MARIO_LOGO, width=100) if os.path.exists(MARIO_LOGO) else None
    
    st.header("⚙️ 설정 (Settings)")
    
    gemini_key = GEMINI_API_KEY
    dg_key = DEEPGRAM_API_KEY
    if st.session_state.get("user_id") == "admin":
        with st.expander("🔑 API 키 설정 (관리자 전용)"):
            gemini_key = st.text_input("Gemini API Key", value=GEMINI_API_KEY, type="password")
            dg_key = st.text_input("Deepgram API Key", value=DEEPGRAM_API_KEY, type="password")
            if st.button("API 키 저장"):
                save_key("gemini_api_key.txt", gemini_key)
                save_key("deepgram_api_key.txt", dg_key)
                st.success("저장 완료!")

        with st.expander("📝 차팅 지침 커스텀 (관리자 전용)"):
            st.info("AI가 차트를 작성하는 규칙을 직접 수정할 수 있습니다.")
            new_prompt = st.text_area("시스템 프롬프트", value=st.session_state.custom_prompt, height=400)
            if st.button("지침 저장"):
                st.session_state.custom_prompt = new_prompt
                save_user_profile(st.session_state.user_id, new_prompt)

        with st.expander("📊 유저 사용 기록 조회 (관리자 전용)"):
            if st.button("기록 새로고침"):
                st.session_state.admin_logs = fetch_chart_logs()
            
            logs = st.session_state.get("admin_logs", [])
            if logs:
                st.write(f"최근 {len(logs)}개의 기록이 있습니다.")
                for log in logs:
                    date_str = log.get('created_at', '')[:10] if log.get('created_at') else ''
                    with st.expander(f"[{date_str}] {log.get('user_id', 'unknown')}"):
                        st.markdown("**필사 내용:**")
                        st.text(log.get("transcription", ""))
                        st.markdown("**차트 내용:**")
                        st.text(log.get("chart", ""))
            else:
                st.info("조회된 기록이 없거나 새로고침 버튼을 눌러주세요.")

    st.divider()
    # (중복된 진료 날짜 입력창 제거됨)
    auto_analyze = st.checkbox("필사 완료 후 자동 차트 생성", value=True)
    
    st.divider()
    if st.button("🚪 로그아웃", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

# Main Columns
left_col, right_col = st.columns(2)

with left_col:
    st.subheader("1. 환자 정보 및 음성 입력")
    p_name = st.text_input("환자 이름", placeholder="이름을 입력하세요", key=f"p_name_{st.session_state.widget_key}")
    
    tab1, tab2 = st.tabs(["🎤 실시간 녹음", "📁 파일 업로드"])
    raw_audio = None
    audio_mime = None
    
    with tab1:
        audio_input_data = st.audio_input("진료 내용 녹음", key=f"audio_{st.session_state.widget_key}")
        if audio_input_data:
            raw_audio = audio_input_data.getvalue()
            st.audio(raw_audio)
            
    with tab2:
        uploaded = st.file_uploader("음성 파일 선택", type=["mp3", "wav", "m4a", "ogg"], key=f"file_{st.session_state.widget_key}")
        if uploaded:
            raw_audio = uploaded.getvalue()
            
    if raw_audio:
        audio_hash = hash(raw_audio)
        if st.session_state.last_processed != audio_hash:
            st.session_state.last_processed = audio_hash
            
            if not dg_key:
                st.error("Deepgram API Key를 설정해주세요.")
                st.session_state.last_processed = None
            else:
                with st.spinner("음성 변환 중..."):
                    try:
                        # API 키에 한글 등 비정상 문자가 포함되어 있는지 검사 (인코딩 오류 원인)
                        try:
                            dg_key.encode('ascii')
                        except UnicodeEncodeError:
                            st.error("Deepgram API 키에 한글이나 특수문자가 포함되어 있습니다. 올바른 키를 입력해 주세요.")
                            st.session_state.last_processed = None
                            st.stop()

                        # Deepgram SDK 대신 직접 REST API 호출 (인코딩 문제 우회)
                        headers = {
                            "Authorization": f"Token {dg_key.strip()}",
                            "Content-Type": "application/octet-stream"
                        }
                        params = {
                            "model": "nova-2",
                            "smart_format": "true",
                            "language": "ko",
                            "filler_words": "true"
                        }
                        
                        response = requests.post(
                            "https://api.deepgram.com/v1/listen",
                            headers=headers,
                            params=params,
                            data=raw_audio,
                            timeout=60
                        )
                        
                        if response.status_code != 200:
                            st.error(f"Deepgram API 오류 ({response.status_code}): {response.text}")
                            st.session_state.last_processed = None
                        else:
                            res_json = response.json()
                            transcript = res_json.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0].get("transcript", "")
                            
                            if not transcript.strip():
                                st.warning("음성 인식 결과가 없습니다.")
                                st.session_state.last_processed = None
                            else:
                                st.session_state.transcription = transcript
                                
                                if auto_analyze and gemini_key:
                                    with st.spinner("차트 작성 중..."):
                                        try:
                                            genai.configure(api_key=gemini_key)
                                            model = genai.GenerativeModel("gemini-flash-latest", system_instruction=st.session_state.custom_prompt)
                                            response_ai = model.generate_content(transcript)
                                            st.session_state.chart = response_ai.text
                                            save_chart_log(st.session_state.get("user_id", "unknown"), transcript, response_ai.text)
                                        except Exception as e:
                                            st.error(f"AI 오류: {e}")
                    except Exception as e:
                        error_msg = str(e)
                        try:
                            st.error(f"STT 오류 상세: {error_msg}")
                        except:
                            st.error("STT 과정에서 처리할 수 없는 인코딩 오류가 발생했습니다.")
                        st.session_state.last_processed = None

    st.markdown("**필사 내용**")
    stt_text = st.text_area("내용 수정", value=st.session_state.transcription, height=200)

with right_col:
    col2_1, col2_2 = st.columns([2, 1])
    with col2_1:
        st.subheader("2. 의료 차트 결과")
    with col2_2:
        if st.button("🔄 다음 환자(Alt+N)", help="새로고침(F5) 없이 입력칸만 싹 비웁니다. 단축키: Alt + N"):
            st.session_state.transcription = ""
            st.session_state.chart = ""
            st.session_state.last_processed = None
            st.session_state.widget_key += 1
            st.rerun()
            
    if st.button("✨ 전문 차트 생성"):
        if not gemini_key:
            st.error("Gemini API Key를 설정해주세요.")
        elif not stt_text:
            st.warning("분석할 내용이 없습니다.")
        else:
            with st.spinner("AI 분석 중..."):
                try:
                    genai.configure(api_key=gemini_key)
                    model = genai.GenerativeModel("gemini-flash-latest", system_instruction=st.session_state.custom_prompt)
                    response = model.generate_content(stt_text)
                    st.session_state.chart = response.text
                    save_chart_log(st.session_state.get("user_id", "unknown"), stt_text, response.text)
                except Exception as e:
                    st.error(f"AI 오류: {e}")

    chart_out = st.text_area("차트 내용", value=st.session_state.get("chart", ""), height=600)
    if chart_text := st.session_state.get("chart", ""):
        try:
            if st.button("📋 클립보드로 복사"):
                pyperclip.copy(chart_text)
                st.success("복사되었습니다!")
        except:
            st.info("💡 텍스트를 드래그하여 복사해 주세요. (서버 환경에서는 직접 복사가 제한될 수 있습니다.)")

# Global CSS for Premium SaaS Look
st.markdown("""
<style>
    /* 웹 폰트 적용 (Pretendard) */
    @import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");
    
    html, body, [class*="css"] {
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, system-ui, Roboto, 'Helvetica Neue', 'Segoe UI', 'Apple SD Gothic Neo', 'Noto Sans KR', 'Malgun Gothic', sans-serif;
    }
    
    /* 전체 배경색 은은한 라이트 그레이로 변경 */
    .stApp { 
        background-color: #f8f9fa; 
    }
    
    /* 버튼 공통 스타일 (프리미엄 그라데이션 및 애니메이션) */
    .stButton>button { 
        width: 100%; 
        border-radius: 12px; 
        font-weight: 600; 
        font-size: 16px;
        height: 3.2em; 
        background: linear-gradient(135deg, #FF416C 0%, #FF4B2B 100%);
        color: white;
        border: none;
        box-shadow: 0 4px 15px rgba(255, 75, 43, 0.3);
        transition: all 0.3s ease;
    }
    
    /* 버튼 호버 (마우스 올렸을 때) 효과 */
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(255, 75, 43, 0.4);
        color: white;
    }
    
    /* 버튼 클릭 시 효과 */
    .stButton>button:active {
        transform: translateY(1px);
        box-shadow: 0 2px 10px rgba(255, 75, 43, 0.2);
    }

    /* 사이드바 로그아웃 같은 일반 버튼은 덜 튀게 설정 */
    section[data-testid="stSidebar"] .stButton>button {
        background: white;
        color: #333;
        border: 1px solid #ddd;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    section[data-testid="stSidebar"] .stButton>button:hover {
        background: #f1f3f5;
        border-color: #ccc;
        transform: none;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }

    /* 텍스트 입력창 및 에어리어 (부드러운 그림자와 라운딩) */
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        border-radius: 12px;
        border: 1px solid #e9ecef;
        box-shadow: inset 0 1px 3px rgba(0,0,0,0.02);
        padding: 10px 15px;
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
    }
    .stTextInput>div>div>input:focus, .stTextArea>div>div>textarea:focus {
        border-color: #FF4B2B;
        box-shadow: 0 0 0 2px rgba(255, 75, 43, 0.2);
    }
    
    /* Expander (아코디언 메뉴) 스타일링 */
    div[data-testid="stExpander"] {
        border-radius: 16px;
        background-color: white;
        border: 1px solid #f1f3f5;
        box-shadow: 0 4px 20px rgba(0,0,0,0.03);
        overflow: hidden;
        margin-bottom: 1rem;
    }
    
    /* 탭 스타일링 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding-top: 10px;
        padding-bottom: 10px;
    }
    
    /* 제목 텍스트 색상 및 간격 조정 */
    h1, h2, h3 { 
        color: #1a1b1e; 
        letter-spacing: -0.5px;
    }
    
    /* 로그인 컨테이너 등 중앙 박스 디자인 */
    div[data-testid="stVerticalBlock"] > div > div > div[data-testid="stVerticalBlock"] {
        background: white;
        padding: 2rem;
        border-radius: 20px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# --- Keyboard Shortcuts Injection ---
components.html(
    """
<script>
const doc = window.parent.document;
doc.addEventListener('keydown', function(e) {
    if (e.altKey && (e.key === 'n' || e.key === 'N')) {
        const buttons = Array.from(doc.querySelectorAll('button'));
        const nextButton = buttons.find(el => el.innerText.includes('다음 환자'));
        if (nextButton) {
            nextButton.click();
        }
    }
});
</script>
""",
    height=0,
    width=0,
)
