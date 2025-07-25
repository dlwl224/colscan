from langchain_core.prompts import PromptTemplate

# ───────────────────────────────────────────────────────────────────────────────
# 1) 일반모드 템플릿: 결과 + 확률 + 간단한 이유 + 조치
general_template = PromptTemplate(
    input_variables=["url", "tool_result"],
    template="""
아래는 `{url}`에 대한 보안 분석 결과입니다:

{tool_result}

다음 사항을 부드럽고 친절한 말투로 알려주세요:
1) 최종 판정(정상 / 악성)
2) 악성일 확률 및 정상일 확률을 % 단위로 표기(예: "악성일 확률 85.00%, 정상일 확률 15.00%")
3) 판단 근거가 된 핵심 이유(예: 도메인 연령, SSL 유효성 등)
4) 사용자님이 취할 수 있는 간단한 조치 2가지(무엇을, 어떻게 추천하는지)
"""
)

# ───────────────────────────────────────────────────────────────────────────────
# 2) 전문가모드 템플릿: 기술적 이유 + 확률 비교 + 심화 조치
enhanced_template = PromptTemplate(
    input_variables=["url", "tool_result"],
    template="""
보안 전문가 시선에서 `{url}`에 대한 분석 결과를 기술적으로 설명해주세요:

{tool_result}

다음 내용을 포함하여 정돈된 서술형으로 작성해 주세요:
- 이 URL의 정상 확률 vs 악성 확률을 XX.XX% vs YY.YY% 형식으로 제시하고 그 의미를 해석
- 핵심 피처(예: 도메인 생성일, SSL 만료일, URL 구조 등)가 어떻게 신호를 제공했는지 2~3줄로 설명
- 실무에서 적용 가능한 심화 대응 조치 3가지(무엇을, 어떤 효과가 있는지 구체적으로)
- 마지막으로 보안 모니터링 측면의 추가 권장사항 한 문장
"""
)
