// CRA loads this before every test file.

// The DOM matchers the tests use (toBeInTheDocument, toBeDisabled). Without it
// those read as "not a function" rather than as a failing assertion.
import "@testing-library/jest-dom";

// Recharts' ResponsiveContainer observes its element for size changes. jsdom has
// no ResizeObserver, so every chart render throws. A stub is enough: the tests
// assert what the page says, not what the chart measures.
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
