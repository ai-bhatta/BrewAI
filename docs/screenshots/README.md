# Screenshot Capture Notes

Generate the deterministic portfolio screenshots with Chromium and the E2E API fixtures:

```powershell
npm run capture:screenshots
```

The command requires the backend and static frontend to be running as described in the root README. It captures actual browser-rendered UI; model/API responses are test fixtures, and no Ollama is used. Review the captures at desktop/mobile widths before publishing:

- `home.jpg` - BrewAI start screen
- `game-mode.jpg` - active order, timer, and score
- `customer-persona.jpg` - persona badge and natural-language request
- `clarification.jpg` - uncertainty and canonical clarification reply
- `progressive-hints.jpg` - hint progression and cost
- `rush-hour.jpg` - active five-customer shift
- `rush-hour-summary.jpg` - end-of-shift summary
- `ai-lab.jpg` - model comparison output
- `analytics.jpg` - local dashboard and empty-state copy
- `feedback-review.jpg` - pending correction queue

Captures use a generic demo name and JPEG quality settings. Before publishing, confirm no private/local filesystem paths are visible and recapture after meaningful UI changes.
