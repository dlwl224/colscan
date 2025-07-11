function goTo(page) {
    alert(`${page} 페이지로 이동합니다.`); // 향후 라우팅 연동 가능
}

// QR 카메라 연동 예시
const video = document.getElementById('camera');
if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
        .then(function (stream) {
            video.srcObject = stream;
            video.play();
        })
        .catch(function (err) {
            alert("카메라 접근 실패: " + err);
        });
}
