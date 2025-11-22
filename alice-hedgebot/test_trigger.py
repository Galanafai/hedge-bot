from agents.agent_oracle import fetch_market_risk

print("--- Testing Force Trigger ---")
report = fetch_market_risk("neo", force_trigger=True)
print(f"\nRisk Level: {report.risk_level}")
print(f"Recommendation: {report.recommendation}")

if report.risk_level == "CRITICAL" and report.recommendation == "HEDGE_NOW":
    print("\n✅ Force trigger working correctly!")
else:
    print("\n❌ Force trigger FAILED!")
