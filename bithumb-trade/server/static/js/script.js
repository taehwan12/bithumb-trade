// ===== 1. 전역 변수 및 설정 =====
const UPDATE_INTERVAL = 2000; // 2초마다 갱신
let priceChart; // 차트 객체 저장 변수

// ===== 2. 유틸 함수 =====
function formatKRW(value) {
    if (value === undefined || value === null) return "₩0";
    return "₩" + Number(value).toLocaleString();
}

// ===== 3. 차트 관련 함수 (시각화) =====
function initChart() {
    const ctx = document.getElementById('btcChart').getContext('2d');

    priceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'BTC Price',
                data: [],
                borderColor: '#2563eb',
                backgroundColor: 'rgba(37, 99, 235, 0.1)',
                borderWidth: 2,
                tension: 0.4,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { display: false },
                y: { position: 'right' }
            },
            animation: false
        }
    });
}

function updateChart(price) {
    if (!priceChart) return;

    const now = new Date().toLocaleTimeString();

    priceChart.data.labels.push(now);
    priceChart.data.datasets[0].data.push(price);

    // 데이터 30개 유지 (메모리 관리)
    if (priceChart.data.labels.length > 30) {
        priceChart.data.labels.shift();
        priceChart.data.datasets[0].data.shift();
    }

    priceChart.update();
}

// ===== 4. API 데이터 연동 (Async/Await) =====

// (1) 자산 및 가격 정보 조회
async function fetchBalance() {
    try {
        // 친구 서버 주소 (로컬 개발 환경 가정)
        // 만약 서버 주소가 다르면 '/api/balance' 앞에 주소를 붙여야 함 (예: 'http://localhost:5000/api/balance')
        const response = await fetch('/api/balance');

        if (!response.ok) throw new Error("서버 응답 오류");

        const data = await response.json();

        if (data) {
            // 텍스트 업데이트
            document.getElementById("krwBalance").innerText = formatKRW(data.krw_balance);
            document.getElementById("btcHolding").innerText = data.btc_balance + " BTC";
            document.getElementById("btcPrice").innerText = formatKRW(data.btc_price);
            document.getElementById("totalAsset").innerText = formatKRW(data.total_assets);

            // ✨ 핵심: 서버에서 받은 실제 가격으로 차트 업데이트
            updateChart(data.btc_price);
        }
    } catch (error) {
        console.error("자산 정보 로딩 실패:", error);
        // 실제 배포 시에는 사용자에게 조용히 실패를 알리거나 재시도 로직 필요
    }
}

// (2) 거래 기록 조회 (보안 적용됨)
async function fetchTrades() {
    try {
        const response = await fetch('/api/trades');
        if (!response.ok) throw new Error("서버 응답 오류");

        const trades = await response.json();
        const tbody = document.getElementById("tradeTableBody");

        tbody.innerHTML = ""; // 초기화

        if (!trades || trades.length === 0) {
            tbody.innerHTML = "<tr><td colspan='5'>거래 기록이 없습니다.</td></tr>";
            return;
        }

        trades.forEach((trade) => {
            const row = document.createElement("tr");

            // 날짜 포맷팅
            let timeStr = "-";
            if (trade.created_at) {
                const dateObj = new Date(trade.created_at);
                timeStr = `${dateObj.getMonth() + 1}/${dateObj.getDate()} ${dateObj.getHours()}:${dateObj.getMinutes()}`;
            }

            // 헬퍼 함수: 텍스트 노드로 안전하게 삽입 (XSS 방어)
            const addCell = (text, color = null, bold = false) => {
                const td = document.createElement("td");
                td.textContent = text;
                if (color) td.style.color = color;
                if (bold) td.style.fontWeight = "bold";
                row.appendChild(td);
            };

            addCell(timeStr);

            // 매수/매도 색상 처리
            const typeText = trade.side ? trade.side.toUpperCase() : "-";
            const typeColor = trade.side === 'buy' ? '#ef4444' : '#3b82f6'; // 빨강/파랑
            addCell(typeText, typeColor, true);

            addCell(formatKRW(trade.price));
            addCell(trade.amount); // 수량
            addCell(trade.reason || '조건 부합'); // 상태/이유

            tbody.appendChild(row);
        });

    } catch (error) {
        console.error("매매 기록 로딩 실패:", error);
    }
}

// ===== 5. 버튼 이벤트 핸들러 (입력값 검증 + 알림) =====

// (1) 전략 저장 버튼
document.querySelector(".save-btn").addEventListener("click", function () {
    // 1차: 클라이언트 측 유효성 검사 (잘못된 입력 방지)
    const buyPercent = Number(document.getElementById("buyPercent").value);
    const sellPercent = Number(document.getElementById("sellPercent").value);

    if (sellPercent <= buyPercent) {
        alert("⚠️ 위험: 매도 조건(%)이 매수 조건보다 낮거나 같습니다. 손실이 발생할 수 있습니다.");
        return;
    }

    // 2차: 서버 전송 (현재 미구현 상태 알림)
    alert("현재 전략 저장 기능은 서버와 연동되지 않았습니다.\n(서버의 autotrade.py 설정이 우선 적용됩니다.)");
});

// (2) 자동매매 스위치
const autoToggle = document.getElementById("autoToggle");
autoToggle.addEventListener("change", function (e) {
    alert("웹 제어 기능 준비 중: 터미널에서 봇을 직접 실행해주세요.");
    // 스위치 강제 복구 (UI만 켜지는 것 방지)
    e.target.checked = !e.target.checked;
});

// ===== 6. 초기화 =====
document.addEventListener("DOMContentLoaded", function () {
    console.log("Dashboard Started.");

    initChart();     // 차트 생성
    fetchBalance();  // 데이터 1회 요청
    fetchTrades();   // 기록 1회 요청

    // 주기적 데이터 갱신 (Polling)
    setInterval(() => {
        fetchBalance();
        fetchTrades();
    }, UPDATE_INTERVAL);
});
