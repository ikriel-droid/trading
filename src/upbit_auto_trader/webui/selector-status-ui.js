(function () {
  function buildSelectorStatus(selectorPayload) {
    const activeSummary = selectorPayload?.active_market_summary || {};
    const pendingOrder = activeSummary?.pending_order || null;
    const position = activeSummary?.position || null;
    const topCandidate = (selectorPayload?.last_scan_results || [])[0] || null;

    if (pendingOrder) {
      if (String(pendingOrder.side || "").toLowerCase() === "ask") {
        return {
          label: "매도 주문 대기",
          tone: "warn",
          message: "매도 주문이 들어가 있어서 체결 또는 취소를 기다리는 중입니다.",
        };
      }
      return {
        label: "매수 주문 대기",
        tone: "warn",
        message: "매수 주문이 들어가 있어서 체결 또는 취소를 기다리는 중입니다.",
      };
    }

    if (position) {
      return {
        label: "보유 중",
        tone: "good",
        message: "현재 선택 종목을 이미 보유 중이라 다음 진입보다 관리와 청산을 우선합니다.",
      };
    }

    if (topCandidate && topCandidate.action === "BUY") {
      return {
        label: "매수 조건 충족",
        tone: "good",
        message: `${topCandidate.market} 가 현재 기준 점수를 넘었습니다. 주문 금액과 보호 장치까지 통과하면 진입할 수 있습니다.`,
      };
    }

    if (selectorPayload?.active_market) {
      return {
        label: "집중 감시 중",
        tone: "active",
        message: `${selectorPayload.active_market} 을(를) 중심으로 다음 신호를 기다리는 중입니다.`,
      };
    }

    return {
      label: "감시 중",
      tone: "active",
      message: "아직 매수 기준을 넘은 후보가 없어 상위 종목을 계속 비교하며 기다리는 중입니다.",
    };
  }

  window.renderSelectorSummary = function renderSelectorSummary(selectorPayload) {
    if (!selectorPayload || !Object.keys(selectorPayload).length) {
      ids.selectorSummary.innerHTML = '<div class="empty-state">자동 종목 선택 결과를 아직 불러오지 못했습니다.</div>';
      return;
    }

    const lastScan = selectorPayload.last_scan_results || [];
    const topCandidate = lastScan[0] || null;
    const selectorStatus = buildSelectorStatus(selectorPayload);

    ids.selectorSummary.innerHTML = `
      <div class="fact-card">
        <div class="chip-row" style="margin-top:0;">
          <span class="chip ${escapeXml(selectorStatus.tone)}">${escapeXml(selectorStatus.label)}</span>
        </div>
        <p class="panel-copy" style="margin-top:10px;">${escapeXml(selectorStatus.message)}</p>
      </div>
      ${buildFactGrid([
        factCard("현재 선택 종목", selectorPayload.active_market || "없음"),
        factCard("후보 종목 수", formatNumber(lastScan.length, 0)),
        factCard("현재 1위 후보", topCandidate?.market || "없음"),
        factCard("1위 점수", topCandidate ? formatNumber(topCandidate.score ?? 0, 1) : "-"),
        factCard("마지막 확정 시각", compactTimestamp(selectorPayload.last_scan_timestamp || "")),
        factCard("자동 선택 상태", selectorStatus.label),
      ])}
    `;
  };

  if (typeof refreshDashboard === "function") {
    window.setTimeout(() => {
      refreshDashboard();
    }, 0);
  }
}());
