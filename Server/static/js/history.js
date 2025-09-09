// static/js/history.js
async function analyzeUrl(url) {
  const response = await fetch("/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url })
  });

  const data = await response.json();

  // ✅ 정상 응답 처리
  if (data.result) {
    alert("분석 결과: " + data.result);
  } else if (data.message) {
    alert(data.message);
  }
}
