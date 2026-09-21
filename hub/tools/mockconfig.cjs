// The preview server serves public/config.js (`{}`), and a production build refuses to fall back to the mock:
// the browser tools answer /config.js the way hub-api does in the sandbox, so the guard and the flows run on
// the same dist the bank ships. Nothing here reaches a real deployment.
const BODY = 'window.__HUB_CONFIG__ = { VITE_API_MODE: "mock", VITE_AUTH_MODE: "mock", HUB_ALLOW_MOCK: true };\n';
module.exports.mockConfig = (page) => page.route("**/config.js", (route) => route.fulfill({ contentType: "application/javascript", body: BODY }));
