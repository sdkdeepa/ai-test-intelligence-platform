import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'

// testing-library's auto-cleanup relies on detecting `afterEach` on
// globalThis, which isn't there since vitest.config.ts doesn't set
// `test.globals: true` (tests import describe/it/expect explicitly instead).
// Wiring it here keeps that explicit style without leaking DOM between tests.
afterEach(cleanup)
