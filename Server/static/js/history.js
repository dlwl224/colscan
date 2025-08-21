// 분석 요청을 보내고 팝업 여부를 확인하는 함수
async function analyzeUrl(url) {
  const response = await fetch("/analyze", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ url: url })
  });

  const data = await response.json();

  // ✅ 10개 초과인 비회원일 경우 로그인 유도 팝업
  if (data.popup) {
    const shouldLogin = confirm("회원 로그인을 하면 전체 기록 확인 가능합니다.\n로그인 하시겠습니까?");
    if (shouldLogin) {
      window.location.href = "/auth/login";
    }
    return;
  }

  // ✅ 정상 분석 결과 처리
  if (data.result) {
    alert("분석 결과: " + data.result);
    // 필요 시 여기에서 화면 업데이트도 가능
  } else if (data.message) {
    alert(data.message);
  }
}
