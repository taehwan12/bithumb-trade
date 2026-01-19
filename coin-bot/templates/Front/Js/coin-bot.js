// ===== mock server data (빗썸 서버 응답 가정) =====
const mockServerData = {
    krwBalance: 1200000,
    btcHolding: 0.032,
    btcPrice: 42350000,
    isAutoTrading: false,
    strategy: {
        buyPercent: 5,
        sellPercent: 10,
        orderAmount: 300000
    },
    tradeHistory: [
        {
            time: "12:03:21",
            type: "BUY",
            price: 41900000,
            amount: 300000,
            status: "Completed"
        }
    ]
};

let lastTradePrice = mockServerData.btcPrice;

let isRequesting = false;

// ===== util =====
function formatKRW(value) {
    return "₩" + value.toLocaleString();
}

// ===== render =====
function renderDashboard(data) {
    document.getElementById("krwBalance").innerText =
        formatKRW(data.krwBalance);

    document.getElementById("btcHolding").innerText =
        data.btcHolding + " BTC";

    document.getElementById("btcPrice").innerText =
        formatKRW(data.btcPrice);

    const totalAsset =
        data.krwBalance + data.btcHolding * data.btcPrice;

    document.getElementById("totalAsset").innerText =
        formatKRW(Math.floor(totalAsset));

    const statusText = document.getElementById("autoStatusText");
    statusText.innerText = data.isAutoTrading
        ? "Auto Trading ON"
        : "Auto Trading OFF";
    statusText.style.color = data.isAutoTrading ? "green" : "red";

    document.getElementById("autoToggle").checked =
        data.isAutoTrading;

    renderTradeHistory(data.tradeHistory);
}

function renderTradeHistory(history) {
    const tbody = document.getElementById("tradeTableBody");
    tbody.innerHTML = "";

    history.forEach((trade) => {
        const row = document.createElement("tr");
        row.innerHTML = `
      <td>${trade.time}</td>
      <td>${trade.type}</td>
      <td>${formatKRW(trade.price)}</td>
      <td>${formatKRW(trade.amount)}</td>
      <td>${trade.status}</td>
    `;
        tbody.appendChild(row);
    });
}

// ===== Auto Trading Toggle =====
const autoToggle = document.getElementById("autoToggle");

autoToggle.addEventListener("change", function () {
    if (isRequesting) {
        autoToggle.checked = mockServerData.isAutoTrading;
        return;
    }

    isRequesting = true;
    autoToggle.disabled = true;

    setTimeout(() => {
        mockServerData.isAutoTrading = autoToggle.checked;
        renderDashboard(mockServerData);

        autoToggle.disabled = false;
        isRequesting = false;
    }, 800);
});

// ===== Save Strategy =====
const saveBtn = document.querySelector(".save-btn");

saveBtn.addEventListener("click", function () {
    if (isRequesting) return;

    const buyPercent = Number(document.getElementById("buyPercent").value);
    const sellPercent = Number(document.getElementById("sellPercent").value);
    const orderAmount = Number(document.getElementById("orderAmount").value);

    if (isNaN(buyPercent) || buyPercent <= 0 || buyPercent > 20) {
        alert("Buy condition must be between 1 and 20%");
        return;
    }

    if (isNaN(sellPercent) || sellPercent <= buyPercent || sellPercent > 30) {
        alert("Sell condition must be greater than buy condition and <= 30%");
        return;
    }

    if (
        isNaN(orderAmount) ||
        orderAmount < 10000 ||
        orderAmount > mockServerData.krwBalance
    ) {
        alert("Invalid order amount");
        return;
    }

    isRequesting = true;
    saveBtn.disabled = true;
    saveBtn.innerText = "Saving...";

    setTimeout(() => {
        mockServerData.strategy = {
            buyPercent,
            sellPercent,
            orderAmount
        };

        saveBtn.disabled = false;
        saveBtn.innerText = "Save Strategy";
        isRequesting = false;

        alert("Strategy saved successfully");
    }, 800);
});

// ===== Init =====
document.addEventListener("DOMContentLoaded", function () {
    renderDashboard(mockServerData);

    document.getElementById("buyPercent").value =
        mockServerData.strategy.buyPercent;
    document.getElementById("sellPercent").value =
        mockServerData.strategy.sellPercent;
    document.getElementById("orderAmount").value =
        mockServerData.strategy.orderAmount;
});

function simulatePriceChange() {
    const changeRate = (Math.random() * 2 - 1) * 0.003; // -0.3% ~ +0.3%
    mockServerData.btcPrice = Math.floor(
        mockServerData.btcPrice * (1 + changeRate)
    );
}

function checkAutoTrading() {
    if (!mockServerData.isAutoTrading) return;

    const price = mockServerData.btcPrice;
    const strategy = mockServerData.strategy;

    // BUY 조건
    if (
        price <= lastTradePrice * (1 - strategy.buyPercent / 100) &&
        mockServerData.krwBalance >= strategy.orderAmount
    ) {
        executeTrade("BUY", price);
    }

    // SELL 조건
    if (
        price >= lastTradePrice * (1 + strategy.sellPercent / 100) &&
        mockServerData.btcHolding > 0
    ) {
        executeTrade("SELL", price);
    }
}

function executeTrade(type, price) {
    const amountKRW = mockServerData.strategy.orderAmount;
    const btcAmount = amountKRW / price;

    if (type === "BUY") {
        mockServerData.krwBalance -= amountKRW;
        mockServerData.btcHolding += btcAmount;
    }

    if (type === "SELL") {
        mockServerData.krwBalance += amountKRW;
        mockServerData.btcHolding -= btcAmount;
    }

    lastTradePrice = price;

    mockServerData.tradeHistory.unshift({
        time: new Date().toLocaleTimeString(),
        type,
        price,
        amount: amountKRW,
        status: "Completed"
    });

    // 로그 최대 10개 유지
    if (mockServerData.tradeHistory.length > 10) {
        mockServerData.tradeHistory.pop();
    }
}

setInterval(() => {
    simulatePriceChange();
    checkAutoTrading();
    renderDashboard(mockServerData);
}, 2000);
