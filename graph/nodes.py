"""
LangGraph Nodes
각 기능을 Node로 정의
"""

from typing import Dict, Any, List
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.types import interrupt
import os
from dotenv import load_dotenv
import random
import json

load_dotenv()


async def setup_game_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    게임 초기 세팅 노드
    - DB에서 캐릭터 정보 로드
    - 무작위 범인 선정
    """
    from backend.database import AsyncSessionLocal
    from backend.crud import get_all_characters

    # DB에서 캐릭터 정보 수집
    async with AsyncSessionLocal() as db:
        db_characters = await get_all_characters(db)
        
    characters = []
    for char in db_characters:
        characters.append({
            "name": char.name,
            # "age" removed as per request
            "job": char.job,
            "personality": char.personality,
            "prompt": char.prompt
        })

    # 무작위 범인 선정
    phantom = random.choice(characters)

    # 초기 생존 상태 및 의심 카운트 설정
    alive_status = {char["name"]: True for char in characters}
    suspicion_counts = {char["name"]: 0 for char in characters}

    return {
        "characters": characters,
        "phantom_name": phantom["name"],
        "round_number": 1,
        "phase": "discussion",
        "day_night": "day",
        "turn_count": 0,
        "messages": [SystemMessage(content="👻 팬텀 로그 시작! 참가자 5명 중 1명이 인간으로 둔갑한 유령 '팬텀'입니다. 밤마다 팬텀은 한 명씩 제거합니다. 팬텀을 찾아내지 못하면 모두가 위험합니다. 지금부터 서로를 관찰하고, 대화하며, 의심스러운 행동을 찾아내세요.")],
        "votes": {},
        "current_speaker": characters[0]["name"],
        "next_speaker": None,
        "user_input": None,
        "user_target": None,
        "accused": None,
        "game_result": None,
        "alive_status": alive_status,
        "suspicion_counts": suspicion_counts,
        "night_logs": [],
        "clues": [],
        "round_summary": "",
        "round_summaries": {},
        "death_log": []
    }


def night_phase_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    밤 페이즈 처리 노드
    - 라운드 증가
    - 희생자 선정 (팬텀 제외, 생존자 중 랜덤)
    - 생존 상태 업데이트
    - 밤 행동 로그 생성
    """
    characters = state.get("characters", [])
    phantom_name = state.get("phantom_name")
    alive_status = state.get("alive_status", {})
    round_number = state.get("round_number", 1)
    
    # 생존자 목록 (팬텀 제외)
    targets = [
        char for char in characters 
        if char["name"] != phantom_name and alive_status.get(char["name"], True)
    ]
    
    night_log_entry = ""
    victim_name = None
    
    if targets:
        # 희생자 선정
        victim = random.choice(targets)
        victim_name = victim["name"]
        
        # 사망 처리
        alive_status[victim_name] = False
        
        # 로그 생성
        night_log_entry = f"Round {round_number} Night: {victim_name}이(가) 습격당해 사망했습니다."
        
        # 시스템 메시지 추가
        message = f"🌙 밤이 지났습니다.\n안타깝게도 {victim_name}이(가) 살해당한 채 발견되었습니다."
        
        # --- 단서 생성 로직 (LLM) ---
        try:
            # 팬텀 정보 가져오기
            phantom_char = next((c for c in characters if c["name"] == phantom_name), None)
            
            if phantom_char:
                llm = ChatGoogleGenerativeAI(
                    model="gemini-2.5-flash",
                    google_api_key=os.getenv("GOOGLE_API_KEY")
                )
                
                clue_prompt = f"""
당신은 추리 소설의 작가입니다.
'팬텀 로그'라는 게임에서 밤사이 살인 사건이 발생했습니다.
팬텀(범인)의 특징을 암시하는 '현장 증거(단서)'를 하나 생성해주세요.

[팬텀 정보]
- 이름: {phantom_char['name']}
- 직업: {phantom_char['job']}
- 성격: {phantom_char['personality']}
- 특징: {phantom_char.get('prompt', '')[:200]}...

[피해자 정보]
- 이름: {victim_name}

[요청사항]
1. 팬텀의 직업이나 성격, 취미와 관련된 미묘한 단서를 만드세요.
2. **절대 팬텀의 이름을 직접 언급하지 마세요.**
3. **직업명을 직접 언급하지 마세요.** (예: "붓" 대신 "물감 냄새", "요리사 모자" 대신 "특이한 향신료")
4. 냄새, 소리, 떨어진 물건, 흔적 등 감각적인 묘사를 사용하세요.
5. 한 문장으로 짧게 작성하세요.

예시:
- (화가가 범인일 때): "피해자의 옷깃에서 희미하게 테레빈유 냄새가 난다."
- (학생이 범인일 때): "현장에 찢어진 전공 서적의 한 페이지가 떨어져 있다."
"""
                response = llm.invoke([HumanMessage(content=clue_prompt)])
                clue_text = response.content.strip()
                
                # 단서 저장
                clues = state.get("clues", [])
                clues.append(f"[Day {round_number+1} 아침 발견] {clue_text}")
                state["clues"] = clues
                
        except Exception as e:
            print(f"Clue Generation Error: {e}")

    else:
        message = "🌙 밤이 지났습니다. 아무 일도 일어나지 않았습니다."

    return {
        "round_number": round_number + 1,
        "phase": "discussion", # 다시 낮 토론으로
        "day_night": "day",
        "alive_status": alive_status,
        "night_logs": [night_log_entry] if night_log_entry else [],
        "clues": state.get("clues", []),
        "messages": [SystemMessage(content=message)],
        "turn_count": 0
    }


def character_speak_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    캐릭터가 말하는 노드
    current_speaker에 해당하는 캐릭터가 발언
    """
    speaker_name = state.get("current_speaker")

    if not speaker_name:
        return state

    # 해당 캐릭터 찾기
    character = None
    for char in state["characters"]:
        if char["name"] == speaker_name:
            character = char
            break

    if not character:
        return state

    # LLM 초기화
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )

    # 시스템 프롬프트 구성
    system_prompt = character["prompt"]

    # 의심 수치 반영
    suspicion_counts = state.get("suspicion_counts", {})
    my_suspicion = suspicion_counts.get(speaker_name, 0)
    
    # 라운드 요약 반영 (기억)
    round_summaries = state.get("round_summaries", {})
    if round_summaries:
        summary_text = "\n".join([f"[Round {r} 요약]: {s}" for r, s in round_summaries.items()])
        system_prompt += f"\n\n[지난 라운드 기억]\n{summary_text}\n"
    
    system_prompt += f"\n\n[상태 정보]\n현재 당신의 의심 수치: {my_suspicion}\n"
    
    # 의심 수치별 감정선 단계화
    if 1 <= my_suspicion <= 2:
        system_prompt += """
[심리 상태: 약간의 신경 쓰임]
누군가 나를 의심하고 있다는 것을 인지했습니다.
- 평소보다 조금 더 신중하게 말하세요.
- "저를 의심하시는 건가요?" 정도로 가볍게 반응하거나, 상황을 살피세요.
"""
    elif 3 <= my_suspicion <= 4:
        system_prompt += """
[심리 상태: 불쾌함 및 방어적]
의심이 커지고 있어 기분이 나쁘고 긴장됩니다.
- 다소 날카롭거나 방어적인 태도를 보이세요.
- "왜 자꾸 저를 몰아가시죠?", "근거 없는 의심은 하지 마세요."라며 불쾌해하세요.
"""
    elif my_suspicion >= 5:
        system_prompt += """
[심리 상태: 극도의 불안 및 패닉]
사람들이 나를 팬텀으로 확신하는 것 같아 매우 불안합니다.
- 목소리가 떨리거나, 감정적으로 격해지세요.
- 억울함을 호소하거나, 강하게 화를 내며 상황을 모면하려 하세요.
"""

    # 범인이라면 특별 지시 추가
    if character["name"] == state["phantom_name"]:
        system_prompt += """

=== 중요: 당신의 역할 ===
🔴 당신은 이번 게임의 **팬텀(살인마)**입니다.

팬텀으로서의 임무:
1. 다른 사람들에게 들키지 않기
2. 평소 성격대로 행동하되, 의심받지 않도록 조심
3. 필요하면 거짓 알리바이를 만들어내기
4. 자연스럽게 다른 사람을 의심하기
========================
"""
        # 팬텀 전용 반응 (의심 수치 3 이상부터)
        if my_suspicion >= 3:
            system_prompt += """
🚨 [위기 상황] 의심 수치가 위험 수준입니다! (3 이상)
당신은 정체가 들킬까 봐 매우 당황하고 있습니다.
- 말이 빨라지거나, 횡설수설하거나, 앞뒤가 안 맞는 말을 하세요.
- "아니, 그게 아니라...", "잠깐만요, 제 말 좀 들어보세요!" 같은 표현을 쓰며 필사적으로 변명하세요.
- 말실수를 하거나 과도하게 화를 내는 것도 좋습니다.
"""
    else:
        # 시민인데 의심받는 경우 (5 이상일 때 더 강력한 반응)
        if my_suspicion >= 5:
            system_prompt += """
🚨 [위기 상황] 억울하게 팬텀으로 몰리고 있습니다! (의심 수치 5 이상)
당신은 결백한데 아무도 믿어주지 않아 답답해 미칠 지경입니다.
- "진짜 아니라니까요!!", "증거를 대보세요!"라며 소리치거나 강하게 호소하세요.
"""

    # 대화 맥락 구성
    conversation = [SystemMessage(content=system_prompt)]

    # 최근 대화 기록 추가 (마지막 5개)
    recent_messages = state.get("messages", [])[-5:]
    conversation.extend(recent_messages)

    # 프롬프트: 짧고 간결하게 발언하기
    prompt = """지금까지의 대화 흐름을 보고, 당신의 성격에 맞게 자연스럽게 한마디 하세요.

**중요 규칙:**
- 반드시 100자 이내로 짧게 말하세요
- 일상 대화처럼 자연스럽게
- 한 번에 한 가지 생각만 표현하세요
- 불필요한 설명은 생략하세요
"""
    conversation.append(HumanMessage(content=prompt))

    # AI 응답 생성
    response = llm.invoke(conversation)

    # 메시지 추가
    new_message = AIMessage(
        content=response.content,
        name=character["name"]
    )

    # 턴 카운트 증가
    new_turn_count = state.get("turn_count", 0) + 1

    return {
        "messages": [new_message],
        "turn_count": new_turn_count
    }


def select_next_speaker_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    다음 발언자를 결정하는 노드 (LLM 기반)
    대화 맥락을 분석하여 가장 적절한 캐릭터를 선정함
    """
    messages = state.get("messages", [])
    characters = state.get("characters", [])
    alive_status = state.get("alive_status", {})
    current_speaker = state.get("current_speaker")
    suspicion_counts = state.get("suspicion_counts", {})
    
    # 생존한 캐릭터 이름 목록
    alive_names = [char["name"] for char in characters if alive_status.get(char["name"], True)]
    
    if not alive_names:
        return {}
        
    # LLM 초기화
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )
    
    # 최근 대화 (마지막 5개)
    recent_messages = messages[-5:]
    
    # 프롬프트 구성
    prompt = f"""
현재 생존자: {', '.join(alive_names)}
직전 발언자: {current_speaker}

[의심 수치]
{json.dumps(suspicion_counts, ensure_ascii=False)}

최근 대화:
"""
    for msg in recent_messages:
        sender = msg.name if hasattr(msg, 'name') else "System"
        prompt += f"- {sender}: {msg.content}\n"
        
    prompt += """
위 대화 흐름을 보고, 다음으로 말하기에 가장 적절한 캐릭터의 이름을 하나만 출력하세요.

**선정 기준:**
1. 직전 발언이 특정인에게 질문했다면, 그 사람이 대답해야 합니다.
2. 최근에 말을 적게 한 캐릭터를 선정하세요.(대화의 흐름을 해치지않게 자연스럽게 끼어든다거나 대화를 이어받는다거나)
3. 대화의 흐름상 가장 자연스럽게 이어받을 사람을 선택하세요.
4. 직전 발언자는 가급적 제외하세요 (연속 발언 지양).


**출력 형식:**
캐릭터 이름만 딱 하나 출력하세요. (예: "김철수")
"""

    # LLM 호출
    response = llm.invoke([HumanMessage(content=prompt)])
    next_speaker = response.content.strip()
    
    # 유효성 검사 (생존자 목록에 있는지)
    found = False
    for name in alive_names:
        if name in next_speaker:
            next_speaker = name
            found = True
            break
            
    if not found:
        # 실패 시 랜덤 선정 (직전 발언자 제외 노력)
        candidates = [n for n in alive_names if n != current_speaker]
        if not candidates:
            candidates = alive_names
        next_speaker = random.choice(candidates)
        
    return {"current_speaker": next_speaker}


def user_input_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    유저 입력 처리 노드
    사용자가 입력한 후 다음 라운드로 진행
    """
    user_input = state.get("user_input", "")

    if not user_input:
        return state

    # 종료 명령어 처리 (1:1 모드에서 복귀)
    if user_input.lower() in ["q", "exit", "quit"]:
        return {
            "phase": "discussion",
            "user_input": None,
            "messages": [SystemMessage(content="1:1 대화를 종료하고 토론 모드로 돌아갑니다.")]
        }

    # 유저 메시지 추가
    user_message = HumanMessage(
        content=user_input,
        name="유저"
    )

    # 다음 라운드로 진행
    current_round = state.get("round_number", 1)
    
    # 기본 업데이트 값
    updates = {
        "messages": [user_message],
        "user_input": None,  # 초기화
        "turn_count": 0,  # 턴 카운트 리셋
        # round_number는 여기서 증가시키지 않음 (밤에만 증가)
    }

    # 현재 페이즈가 one_on_one이면 페이즈 유지
    if state.get("phase") == "one_on_one":
        updates["phase"] = "one_on_one"
        
        # 1:1 모드에서는 특정 대상 지목 로직 유지
        import re
        match = re.search(r"\[(.*?)에게\]", user_input)
        if match:
            target_name = match.group(1)
            characters = state.get("characters", [])
            for char in characters:
                if char["name"] == target_name:
                    updates["current_speaker"] = target_name
                    break
    elif state.get("phase") == "free_discussion":
        updates["phase"] = "free_discussion"
        # free_discussion 모드에서는 특정 대상 지목 로직 제거 (select_next_speaker_node가 처리)
    else:
        updates["phase"] = "discussion"
        # discussion 모드에서는 특정 대상 지목 로직 제거
        # 다음 화자는 select_next_speaker_node에서 결정됨

    return updates


def vote_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    투표 처리 노드
    """
    user_target = state.get("user_target")
    phantom_name = state.get("phantom_name")

    if not user_target:
        return state

    # 결과 판정
    if user_target == phantom_name:
        result = "win"
        message = f"🎉 정답입니다! {user_target}이(가) 팬텀이었습니다!"
    else:
        result = "lose"
        message = f"😢 틀렸습니다. {user_target}은(는) 팬텀이 아닙니다. 진짜 팬텀은 {phantom_name}입니다."

    return {
        "accused": user_target,
        "game_result": result,
        "phase": "end",
        "messages": [SystemMessage(content=message)]
    }


def next_turn_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    다음 턴으로 진행
    (사실상 discussion 모드에서는 select_next_speaker가 역할을 대신하지만,
     기존 로직 호환성을 위해 유지)
    """
    return {}


def wait_for_user_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    사용자 입력을 기다리는 노드
    LangGraph interrupt를 트리거해 그래프 실행을 일시 중단한다.
    """
    resume_data = interrupt("wait_user")
    
    if resume_data is not None:
        return resume_data
        
    return state


def suspicion_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    사용자가 특정 캐릭터를 의심하는 노드
    """
    target_name = state.get("user_target")
    suspicion_counts = state.get("suspicion_counts", {})
    
    if target_name and target_name in suspicion_counts:
        suspicion_counts[target_name] += 1
        message = f"👁️ 유저가 {target_name}을(를) 의심합니다. (의심 수치: {suspicion_counts[target_name]})"
    else:
        message = "⚠️ 의심 대상을 찾을 수 없습니다."
        
    return {
        "suspicion_counts": suspicion_counts,
        "messages": [SystemMessage(content=message)],
        "user_target": None, # 타겟 초기화
        "user_input": None   # 입력 초기화
    }


def ai_suspicion_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    라운드 종료 시 AI들이 서로를 의심하는 노드
    """
    messages = state.get("messages", [])
    characters = state.get("characters", [])
    alive_status = state.get("alive_status", {})
    suspicion_counts = state.get("suspicion_counts", {})
    
    # 생존자 목록
    alive_names = [char["name"] for char in characters if alive_status.get(char["name"], True)]
    
    if len(alive_names) < 2:
        return {}

    # LLM 초기화
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )
    
    # 최근 대화 분석 (최대 20개)
    recent_messages = messages[-20:]
    
    prompt = f"""
현재 생존자: {', '.join(alive_names)}

최근 대화 내용을 바탕으로, AI 캐릭터들이 서로를 의심할 만한 상황인지 분석하세요.
각 캐릭터별로 적극적으로 가장 의심스러운 사람을 1명씩 지목하거나, 없으면 "None"을 선택하세요.

**분석 기준:**
1. 말이 앞뒤가 안 맞거나, 거짓말을 하는 것 같은 사람
2. 지나치게 방어적이거나, 반대로 지나치게 공격적인 사람
3. 팬텀 같은 행동을 보인 사람

**출력 형식 (JSON):**
{{
    "의심행동": [
        {{"suspect": "의심하는사람이름", "target": "의심받는사람이름", "reason": "이유"}}
    ]
}}
주의: "suspect"와 "target"은 반드시 생존자 이름이어야 합니다.
"""

    for msg in recent_messages:
        sender = msg.name if hasattr(msg, 'name') else "System"
        prompt += f"- {sender}: {msg.content}\n"
        
    response = llm.invoke([HumanMessage(content=prompt)])
    
    try:
        # JSON 파싱 시도
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
            
        result = json.loads(content)
        suspicion_updates = []
        
        for item in result.get("의심행동", []):
            suspect = item.get("suspect")
            target = item.get("target")
            
            if suspect in alive_names and target in alive_names and suspect != target:
                suspicion_counts[target] += 1
                suspicion_updates.append(f"{suspect} -> {target} 의심 (+1)")
                
        if suspicion_updates:
            summary = "🕵️ [AI 의심 현황]\n" + "\n".join(suspicion_updates)
            return {
                "suspicion_counts": suspicion_counts,
                "messages": [SystemMessage(content=summary)]
            }
            
    except Exception as e:
        print(f"AI Suspicion Error: {e}")
        
    return {}


def summarize_round_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    라운드 요약 및 메모리 관리 노드
    - 현재 라운드의 주요 사건 요약
    - 요약본 저장
    - 메시지 히스토리 초기화 (토큰 관리)
    """
    messages = state.get("messages", [])
    round_number = state.get("round_number", 1)
    round_summaries = state.get("round_summaries", {})
    night_logs = state.get("night_logs", [])
    suspicion_counts = state.get("suspicion_counts", {})
    
    # LLM 초기화
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.getenv("GOOGLE_API_KEY")
    )
    
    # 요약 프롬프트 구성
    prompt = f"""
[Round {round_number} 요약 요청]

다음은 이번 라운드(Day {round_number})의 전체 대화 및 사건 기록입니다.
이 내용을 바탕으로 다음 라운드에서 캐릭터들이 기억해야 할 핵심 내용을 요약해주세요.

[대화 기록]
"""
    for msg in messages:
        sender = msg.name if hasattr(msg, 'name') else "System"
        prompt += f"- {sender}: {msg.content}\n"
        
    prompt += f"""
[밤 행동 로그]
{json.dumps(night_logs, ensure_ascii=False)}

[현재 의심 수치]
{json.dumps(suspicion_counts, ensure_ascii=False)}

**요약 가이드라인:**
1. 누가 누구를 의심했는지, 주요 대립 구도는 무엇이었는지 요약하세요.
2. 사망자가 발생했다면 누구인지 명시하세요.
3. 캐릭터들이 다음 날 아침에 기억해야 할 중요한 단서나 발언을 포함하세요.
4. 전체 길이는 500자 이내로 핵심만 간결하게 작성하세요.
"""

    # 요약 생성
    response = llm.invoke([HumanMessage(content=prompt)])
    summary_text = response.content.strip()
    
    # 요약 저장
    round_summaries[round_number] = summary_text
    
    # 메시지 초기화 (요약본만 남기고 리셋)
    # 다음 라운드 시작 시 시스템 메시지로 요약본을 제공하는 방식
    new_messages = [
        SystemMessage(content=f"=== Round {round_number-1} 요약 ===\n{summary_text}\n=================="),
        SystemMessage(content=f"Day {round_number} 아침이 밝았습니다.")
    ]
    
    return {
        "round_summaries": round_summaries,
        "messages": new_messages,
        "turn_count": 0
    }