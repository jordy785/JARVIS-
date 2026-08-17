"""Technical Analyst agent — multi-timeframe indicator-based analysis."""

from __future__ import annotations

from jarvis.agents.base import Agent, AgentContext
from jarvis.core.enums import AgentOpinion
from jarvis.core.indicators import atr, ema, macd, rsi, sma, support_resistance
from jarvis.core.models import AgentReport


class TechnicalAnalystAgent(Agent):
    name = "TECHNICAL ANALYST"

    TFs = ("M15", "H1", "H4", "D1")

    def _analyze_tf(self, candles) -> dict:
        if len(candles) < 35:
            return {"ok": False, "reason": "insufficient data"}
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]
        r = rsi(closes, 14)
        macd_line, sig, hist = macd(closes)
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        sma200 = sma(closes, 200) if len(closes) >= 200 else None
        sup, res = support_resistance(highs, lows, 20)
        atr_v = atr(highs, lows, closes, 14)

        bull, bear = 0, 0
        if ema20 is not None and ema50 is not None:
            if ema20 > ema50:
                bull += 1
            else:
                bear += 1
        if sma200 is not None:
            if closes[-1] > sma200:
                bull += 1
            else:
                bear += 1
        if r is not None:
            if r < 30:
                bull += 1
            elif r > 70:
                bear += 1
        if hist is not None:
            if hist > 0:
                bull += 1
            elif hist < 0:
                bear += 1
        if sup is not None and res is not None:
            # breakout above resistance?
            if closes[-1] > res * 0.999:
                bull += 1
            elif closes[-1] < sup * 1.001:
                bear += 1
        return {
            "ok": True,
            "rsi": r,
            "macd_hist": hist,
            "ema20": ema20,
            "ema50": ema50,
            "sma200": sma200,
            "support": sup,
            "resistance": res,
            "atr": atr_v,
            "bull": bull,
            "bear": bear,
        }

    def analyze(self, context: AgentContext) -> AgentReport:
        total_bull, total_bear, tf_results = 0, 0, {}
        for tf in self.TFs:
            candles = context.candles(timeframe=tf, count=210)
            res = self._analyze_tf(candles)
            tf_results[tf] = res
            if res.get("ok"):
                total_bull += res["bull"]
                total_bear += res["bear"]

        if total_bull > total_bear:
            opinion = AgentOpinion.BUY
        elif total_bear > total_bull:
            opinion = AgentOpinion.SELL
        else:
            opinion = AgentOpinion.NEUTRAL
        confidence = self._clamp(0.4 + 0.05 * abs(total_bull - total_bear))

        reasoning = "; ".join(
            f"{tf}: bull={r.get('bull',0)} bear={r.get('bear',0)}"
            + ("" if r.get("ok") else f" [{r.get('reason','')}]")
            for tf, r in tf_results.items()
        )
        return AgentReport(
            agent_name=self.name,
            opinion=opinion,
            confidence=confidence,
            reasoning=reasoning,
            metrics={"timeframes": tf_results, "total_bull": total_bull, "total_bear": total_bear},
        )
