// An authenticated local bridge can prepare native sign-in before AuthGate runs.
// Ordinary installations have no preparation promise and use their usual login.
declare global {
  interface Window {
    __workspaceReady?: Promise<unknown>;
  }
}

Promise.resolve(window.__workspaceReady).then(() => import("./index"));

export {};
