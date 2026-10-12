# Release Checklist

- [ ] Fresh clone works with standard venv/pip setup
- [x] Reproducible production training command writes artifact provenance
- [x] Backend starts with a trained production model or keyword fallback
- [x] Frontend starts with Python's static server
- [ ] Game Mode manual smoke test completed in a browser
- [ ] Rush Hour manual smoke test completed in a browser
- [ ] AI Lab manual smoke test completed in a browser
- [ ] Feedback queue manual smoke test completed in a browser
- [ ] Analytics manual smoke test completed in a browser
- [ ] Fixed difficulty manually checked
- [ ] Heuristic difficulty manually checked
- [ ] Contextual-bandit mode manually checked
- [x] Templates work without Ollama (unit and client tests)
- [x] Ollama unavailability has safe template fallback (unit/client tests)
- [x] Full Playwright suite passes with local Chromium (API responses mocked)
- [x] Fixture-backed portfolio screenshots captured
- [x] README setup, limitations, and metric scope documented
- [ ] Docker build/start manually checked

Do not check off browser- or Docker-dependent items based only on mocked tests or static inspection.
