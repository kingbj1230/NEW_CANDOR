const SUPABASE_URL = "https://txumpkghskgiprwqpigg.supabase.co";
const SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR4dW1wa2doc2tnaXByd3FwaWdnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc3NzU1MDksImV4cCI6MjA4MzM1MTUwOX0.kpChb4rlwOU_q8_q9DMn_0ZbOizhmwsjl4rjA9ZCQWk";

let supabaseClient = null;
const AUTO_LOGOUT_IDLE_MS = 3 * 60 * 60 * 1000;
const ACTIVITY_SYNC_MIN_INTERVAL_MS = 2 * 60 * 1000;
const OAUTH_LOGIN_PATH = "/login";
const OAUTH_POST_LOGIN_REDIRECT_PATH = "/";
const AUTH_PASSWORD_MIN_LENGTH = 6;
const FORGOT_PASSWORD_SENDING_LABEL = "메일을 보내는 중입니다.";
const FORGOT_PASSWORD_COOLDOWN_MS = 60 * 1000;
const REMEMBER_LOGIN_ENABLED_KEY = "candor:remember_login_enabled";
const REMEMBER_LOGIN_EMAIL_KEY = "candor:remember_login_email";
const REMEMBER_LOGIN_PASSWORD_KEY = "candor:remember_login_password";
let inactivityTimerId = null;
let autoLogoutRunning = false;
let activitySyncInFlight = false;
let lastActivitySyncAt = 0;
let fetchActivityTrackingBound = false;
let forgotPasswordInFlight = false;
let forgotPasswordLastSentAt = 0;

//supabase 클라이언트를 가져오는 함수
function getSupabaseClient() {
  if (!window.supabase) {
    console.error("Supabase SDK가 로드되지 않았습니다.");
    return null;
  }

  if (!supabaseClient) {
    supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY);
  }

  return supabaseClient;
}

// id 입력값을 공백을 제외하고 가져오도록 하는 함수 
function valueById(id) {
  return document.getElementById(id)?.value?.trim() || "";
}

function getRememberCheckInputs() {
  return [
    document.getElementById("loginRememberLogin"),
    document.getElementById("signupRememberLogin"),
  ].filter(Boolean);
}

function setRememberChecked(checked) {
  getRememberCheckInputs().forEach((input) => {
    input.checked = !!checked;
  });
}

function isRememberChecked() {
  return getRememberCheckInputs().some((input) => input.checked);
}

function loadRememberedLoginInfo() {
  const enabled = localStorage.getItem(REMEMBER_LOGIN_ENABLED_KEY) === "1";
  const rememberedEmail = localStorage.getItem(REMEMBER_LOGIN_EMAIL_KEY) || "";
  const rememberedPassword = localStorage.getItem(REMEMBER_LOGIN_PASSWORD_KEY) || "";
  setRememberChecked(enabled);
  if (!enabled) return;

  const loginEmailInput = document.getElementById("loginEmail");
  const signupEmailInput = document.getElementById("signupEmail");
  const loginPasswordInput = document.getElementById("loginPassword");

  if (rememberedEmail) {
    if (loginEmailInput && !loginEmailInput.value) loginEmailInput.value = rememberedEmail;
    if (signupEmailInput && !signupEmailInput.value) signupEmailInput.value = rememberedEmail;
  }
  if (rememberedPassword && loginPasswordInput && !loginPasswordInput.value) {
    loginPasswordInput.value = rememberedPassword;
  }
}

function persistRememberedLoginInfo(email, password) {
  const shouldRemember = isRememberChecked();
  if (!shouldRemember) {
    localStorage.removeItem(REMEMBER_LOGIN_ENABLED_KEY);
    localStorage.removeItem(REMEMBER_LOGIN_EMAIL_KEY);
    localStorage.removeItem(REMEMBER_LOGIN_PASSWORD_KEY);
    return;
  }

  localStorage.setItem(REMEMBER_LOGIN_ENABLED_KEY, "1");
  if (email) {
    localStorage.setItem(REMEMBER_LOGIN_EMAIL_KEY, email);
  }
  if (typeof password === "string") {
    if (password) localStorage.setItem(REMEMBER_LOGIN_PASSWORD_KEY, password);
    else localStorage.removeItem(REMEMBER_LOGIN_PASSWORD_KEY);
  }
}

function bindRememberLoginOption() {
  const rememberInputs = getRememberCheckInputs();
  if (!rememberInputs.length) return;

  rememberInputs.forEach((input) => {
    input.addEventListener("change", () => {
      setRememberChecked(input.checked);
      if (!input.checked) {
        localStorage.removeItem(REMEMBER_LOGIN_ENABLED_KEY);
        localStorage.removeItem(REMEMBER_LOGIN_EMAIL_KEY);
        localStorage.removeItem(REMEMBER_LOGIN_PASSWORD_KEY);
      } else {
        const email = valueById("loginEmail") || valueById("signupEmail");
        const password = valueById("loginPassword") || valueById("signupPassword");
        persistRememberedLoginInfo(email, password);
      }
    });
  });
}

async function maybeStoreBrowserCredential(email, password) {
  if (!isRememberChecked()) return;
  if (!("credentials" in navigator) || !window.PasswordCredential) return;
  if (!email || !password) return;

  try {
    const credential = new window.PasswordCredential({
      id: email,
      password,
      name: email,
    });
    await navigator.credentials.store(credential);
  } catch (err) {
    console.warn("브라우저 자격 증명 저장 실패:", err?.message || err);
  }
}

function bindPasswordVisibilityToggles() {
  const buttons = Array.from(document.querySelectorAll("[data-toggle-password]"));
  if (!buttons.length) return;

  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.getAttribute("data-toggle-password") || "";
      const input = targetId ? document.getElementById(targetId) : null;
      if (!input) return;
      const isPasswordType = input.type === "password";
      input.type = isPasswordType ? "text" : "password";
      button.textContent = isPasswordType ? "숨기기" : "보기";
      button.setAttribute("aria-pressed", isPasswordType ? "true" : "false");
      button.setAttribute("aria-label", isPasswordType ? "비밀번호 숨기기" : "비밀번호 보기");
    });
  });
}

function getHashParams() {
  const rawHash = String(window.location.hash || "");
  const payload = rawHash.startsWith("#") ? rawHash.slice(1) : rawHash;
  return new URLSearchParams(payload);
}

function isPasswordRecoveryFlow() {
  return getHashParams().get("type") === "recovery";
}

//supabase 로그인상태를 Flask 세션과 동기화하는 함수
async function syncFlaskLogin(accessToken, user = null) {
  if (!accessToken) {
    throw new Error("Supabase access token not found.");
  }
  const resp = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      access_token: accessToken,
      user_id: user?.id || null,
      email: user?.email || null,
    }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Flask 세션 동기화 실패: ${text}`);
  }
}

//supabase 로그아웃 상태를 Flask 세션과 동기화하는 함수
async function syncFlaskLogout(options = {}) {
  const useKeepAlive = !!options.keepalive;
  const resp = await fetch("/auth/logout", {
    method: "POST",
    keepalive: useKeepAlive,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Flask 로그아웃 동기화 실패: ${text}`);
  }
}

// 회원가입 함수
async function handleSignUp(emailArg, passwordArg, nameArg) {
  const client = getSupabaseClient();
  if (!client) return { data: null, error: new Error("Supabase client not initialized") };

  const email = emailArg || valueById("signupEmail") || valueById("email");
  const password = passwordArg || valueById("signupPassword") || valueById("password");
  const name = nameArg || valueById("signupName");

  if (!email || !password) {
    const error = new Error("이메일과 비밀번호를 입력해 주세요.");
    alert(error.message);
    return { data: null, error };
  }

  if (password.length < 6) {
    const error = new Error("비밀번호는 6자 이상이어야 합니다.");
    alert(error.message);
    return { data: null, error };
  }

  const { data, error } = await client.auth.signUp({
    email,
    password,
    options: {
      data: {
        name: name || "",
      },
    },
  });

  if (error) {
    if ((error.message || "").toLowerCase().includes("already")) {
      alert("이미 가입된 이메일입니다. 로그인해 주세요.");
    } else {
      alert("회원가입 실패: " + error.message);
    }
    return { data, error };
  }

  if (data?.user && !data?.session) {
    alert("인증 메일이 발송되었습니다. 메일함을 확인해 주세요.");
  } else {
    alert("회원가입이 완료되었습니다.");
  }

  return { data, error: null };
}

// 로그인 함수
async function handleSignIn(emailArg, passwordArg) {
  const client = getSupabaseClient();
  if (!client) return { data: null, error: new Error("Supabase client not initialized") };

  const email = emailArg || valueById("loginEmail") || valueById("email");
  const password = passwordArg || valueById("loginPassword") || valueById("password");

  if (!email || !password) {
    const error = new Error("이메일과 비밀번호를 입력해 주세요.");
    alert(error.message);
    return { data: null, error };
  }

  const { data, error } = await client.auth.signInWithPassword({
    email,
    password,
  });

  if (error) {
    alert("로그인 실패: " + error.message);
    return { data, error };
  }

  await syncFlaskLogin(data?.session?.access_token, data?.user || null);
  await maybeStoreBrowserCredential(email, password);
  alert(`${data.user.email}님, 환영합니다!`);
  return { data, error: null };
}

// Google OAuth 로그인/회원가입 시작 함수
async function handleGoogleOAuth() {
  const client = getSupabaseClient();
  if (!client) return { data: null, error: new Error("Supabase client not initialized") };

  const redirectTo = `${window.location.origin}${OAUTH_LOGIN_PATH}`;
  const { data, error } = await client.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo,
    },
  });

  if (error) {
    alert("Google 로그인 실패: " + error.message);
    return { data, error };
  }

  return { data, error: null };
}

async function handleForgotPassword(emailArg) {
  const client = getSupabaseClient();
  if (!client) return { data: null, error: new Error("Supabase client not initialized") };

  const email = (emailArg || valueById("loginEmail") || valueById("signupEmail")).trim();
  if (!email) {
    const error = new Error("비밀번호 재설정 메일을 받을 이메일을 입력해 주세요.");
    alert(error.message);
    return { data: null, error };
  }

  const redirectTo = `${window.location.origin}${OAUTH_LOGIN_PATH}`;
  const { data, error } = await client.auth.resetPasswordForEmail(email, { redirectTo });
  if (error) {
    alert("비밀번호 재설정 메일 전송 실패: " + error.message);
    return { data, error };
  }

  alert("비밀번호 재설정 메일을 보냈습니다. 메일함에서 링크를 확인해 주세요.");
  return { data, error: null };
}

async function maybeHandlePasswordRecoveryFlow() {
  if (!isPasswordRecoveryFlow()) return false;

  const newPassword = window.prompt("새 비밀번호를 입력해 주세요. (6자 이상)");
  if (newPassword === null) {
    alert("비밀번호 변경이 취소되었습니다.");
    return true;
  }

  const trimmedPassword = String(newPassword || "").trim();
  if (trimmedPassword.length < AUTH_PASSWORD_MIN_LENGTH) {
    alert(`비밀번호는 ${AUTH_PASSWORD_MIN_LENGTH}자 이상이어야 합니다.`);
    return true;
  }

  const confirmPassword = window.prompt("새 비밀번호를 한 번 더 입력해 주세요.");
  if (confirmPassword === null) {
    alert("비밀번호 변경이 취소되었습니다.");
    return true;
  }
  if (trimmedPassword !== String(confirmPassword || "").trim()) {
    alert("비밀번호 확인 값이 일치하지 않습니다.");
    return true;
  }

  const client = getSupabaseClient();
  if (!client) return true;

  const { error } = await client.auth.updateUser({ password: trimmedPassword });
  if (error) {
    alert("비밀번호 변경 실패: " + error.message);
    return true;
  }

  try {
    await syncFlaskLogout({ keepalive: true });
  } catch (err) {
    console.warn("비밀번호 변경 후 Flask 세션 종료 실패:", err?.message || err);
  }
  try {
    await client.auth.signOut();
  } catch (err) {
    console.warn("비밀번호 변경 후 Supabase 세션 종료 실패:", err?.message || err);
  }

  window.history.replaceState({}, document.title, OAUTH_LOGIN_PATH);
  const loginPasswordInput = document.getElementById("loginPassword");
  if (loginPasswordInput) loginPasswordInput.value = "";
  alert("비밀번호가 변경되었습니다. 새 비밀번호로 다시 로그인해 주세요.");
  return true;
}

// 로그아웃 함수
async function handleSignOut() {
  const client = getSupabaseClient();
  if (!client) return { error: new Error("Supabase client not initialized") };

  const { error } = await client.auth.signOut();
  if (error) {
    alert("로그아웃 실패: " + error.message);
    return { error };
  }

  await syncFlaskLogout();
  return { error: null };
}

async function silentSignOut(options = {}) {
  const client = getSupabaseClient();
  if (client) {
    try {
      await client.auth.signOut();
    } catch (err) {
      console.warn("Supabase silent sign-out 실패:", err?.message || err);
    }
  }
  try {
    await syncFlaskLogout({ keepalive: !!options.keepalive });
  } catch (err) {
    console.warn("Flask silent sign-out 실패:", err?.message || err);
  }
}

//회원가입/로그인한 정보를 JS로 전달해주는 함수
function bindAuthForms() {
  const signupForm = document.getElementById("signupForm");
  if (signupForm) {
    signupForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const email = valueById("signupEmail");
        const password = valueById("signupPassword");
        const { error } = await handleSignUp();
        if (!error) {
          persistRememberedLoginInfo(email, password);
          signupForm.reset();
          const rememberedEmail = localStorage.getItem(REMEMBER_LOGIN_EMAIL_KEY) || "";
          if (rememberedEmail) {
            const signupEmailInput = document.getElementById("signupEmail");
            if (signupEmailInput) signupEmailInput.value = rememberedEmail;
          }
        }
      } catch (err) {
        alert(err?.message || "회원가입 처리 중 오류가 발생했습니다.");
      }
    });
  }

  const loginForm = document.getElementById("loginForm");
  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const email = valueById("loginEmail");
        const password = valueById("loginPassword");
        const { error } = await handleSignIn(email, password);
        if (!error) {
          persistRememberedLoginInfo(email, password);
          window.location.href = "/";
        }
      } catch (err) {
        alert(err?.message || "로그인 처리 중 오류가 발생했습니다.");
      }
    });
  }
}

function bindGoogleOAuthButtons() {
  const buttons = document.querySelectorAll("[data-google-auth]");
  if (!buttons.length) return;

  buttons.forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      if (button.disabled) return;
      button.disabled = true;
      try {
        const { error } = await handleGoogleOAuth();
        if (error) {
          button.disabled = false;
        }
      } catch (err) {
        button.disabled = false;
        alert(err?.message || "Google 로그인 처리 중 오류가 발생했습니다.");
      }
    });
  });
}

function bindForgotPasswordLink() {
  const link = document.querySelector("[data-forgot-password]");
  if (!link) return;
  const defaultLabel = (link.textContent || "").trim() || "비밀번호를 잊으셨나요?";

  const setSendingState = (isSending) => {
    forgotPasswordInFlight = isSending;
    link.textContent = isSending ? FORGOT_PASSWORD_SENDING_LABEL : defaultLabel;
    link.classList.toggle("is-disabled", isSending);
    link.setAttribute("aria-disabled", isSending ? "true" : "false");
  };

  link.addEventListener("click", async (event) => {
    event.preventDefault();
    if (forgotPasswordInFlight) return;

    const now = Date.now();
    if (now - forgotPasswordLastSentAt < FORGOT_PASSWORD_COOLDOWN_MS) {
      const remainSec = Math.max(1, Math.ceil((FORGOT_PASSWORD_COOLDOWN_MS - (now - forgotPasswordLastSentAt)) / 1000));
      alert(`재설정 메일은 잠시 후 다시 요청해 주세요. (${remainSec}초 남음)`);
      return;
    }

    setSendingState(true);
    try {
      const { error } = await handleForgotPassword();
      if (!error) {
        forgotPasswordLastSentAt = Date.now();
      }
    } catch (err) {
      alert(err?.message || "비밀번호 재설정 요청 중 오류가 발생했습니다.");
    } finally {
      setSendingState(false);
    }
  });
}

//브라우저에 저장된 supabase 세션을 Flask 세션과 동기화하는 함수
async function syncInitialAuthState() {
  const client = getSupabaseClient();
  if (!client) return false;

  const { data, error } = await client.auth.getSession();
  if (error) {
    console.error("초기 인증 상태 조회 실패:", error.message);
    return false;
  }

  if (data?.session?.access_token) {
    await syncFlaskLogin(data.session.access_token, data?.session?.user || null);
    return true;
  } else {
    await syncFlaskLogout();
    return false;
  }
}

//로그아웃 버튼과 js 클릭 이벤트 연결
function bindLogoutLink() {
  const links = document.querySelectorAll("[data-supabase-logout]");
  if (!links.length) return;

  links.forEach((link) => {
    link.addEventListener("click", async (e) => {
      e.preventDefault();
      try {
        const { error } = await handleSignOut();
        if (!error) {
          window.location.href = "/login";
        }
      } catch (err) {
        alert(err?.message || "로그아웃 처리 중 오류가 발생했습니다.");
      }
    });
  });
}

// /login#signup 로 진입하면 회원가입 패널을 기본으로 보여주는 함수
function openSignUpPanelFromHash() {
  if (window.location.pathname !== "/login") return;
  if (window.location.hash !== "#signup") return;

  const container = document.getElementById("container");
  if (container) container.classList.add("right-panel-active");
}

function isTrackableApiRequest(input) {
  try {
    const rawUrl = typeof input === "string" ? input : input?.url || "";
    const url = new URL(rawUrl, window.location.href);
    if (url.origin !== window.location.origin) return false;
    return url.pathname.startsWith("/api/") || url.pathname.startsWith("/auth/");
  } catch {
    return false;
  }
}

function bindApiActivityTracking() {
  if (fetchActivityTrackingBound || typeof window.fetch !== "function") return;
  const nativeFetch = window.fetch.bind(window);

  window.fetch = async (...args) => {
    const shouldTrack = isTrackableApiRequest(args[0]);
    if (shouldTrack) resetIdleAutoLogoutTimer();
    try {
      return await nativeFetch(...args);
    } finally {
      if (shouldTrack) resetIdleAutoLogoutTimer();
    }
  };

  fetchActivityTrackingBound = true;
}

async function syncFlaskActivity(force = false) {
  if (!window.APP_CONTEXT?.userId) return;
  if (activitySyncInFlight) return;

  const now = Date.now();
  if (!force && now - lastActivitySyncAt < ACTIVITY_SYNC_MIN_INTERVAL_MS) return;
  lastActivitySyncAt = now;
  activitySyncInFlight = true;

  try {
    const resp = await fetch("/auth/activity", { method: "POST", keepalive: true });
    if (resp.status === 401) {
      throw new Error("session expired");
    }
    if (!resp.ok) {
      throw new Error(`activity sync failed: ${resp.status}`);
    }
  } catch (err) {
    if (String(err?.message || "").includes("session expired")) {
      triggerIdleAutoLogout().catch((logoutErr) => {
        autoLogoutRunning = false;
        console.warn("자동 로그아웃 실패:", logoutErr?.message || logoutErr);
      });
      return;
    }
    console.warn("세션 활동 동기화 실패:", err?.message || err);
  } finally {
    activitySyncInFlight = false;
  }
}

async function triggerIdleAutoLogout() {
  if (autoLogoutRunning) return;
  autoLogoutRunning = true;
  await silentSignOut();
  if (window.location.pathname !== "/login") {
    window.location.href = "/login?reason=idle";
    return;
  }
  autoLogoutRunning = false;
}

function resetIdleAutoLogoutTimer() {
  if (!window.APP_CONTEXT?.userId) return;
  if (inactivityTimerId) {
    window.clearTimeout(inactivityTimerId);
  }
  inactivityTimerId = window.setTimeout(() => {
    triggerIdleAutoLogout().catch((err) => {
      autoLogoutRunning = false;
      console.warn("자동 로그아웃 실패:", err?.message || err);
    });
  }, AUTO_LOGOUT_IDLE_MS);
}

function noteUserActivity() {
  if (!window.APP_CONTEXT?.userId) return;
  resetIdleAutoLogoutTimer();
  syncFlaskActivity().catch((err) => {
    console.warn("세션 활동 동기화 실패:", err?.message || err);
  });
}

function bindIdleAutoLogout() {
  if (!window.APP_CONTEXT?.userId) return;

  const events = ["mousemove", "click", "keydown", "touchstart"];
  events.forEach((name) => {
    window.addEventListener(name, noteUserActivity, { passive: true });
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) noteUserActivity();
  });

  noteUserActivity();
}

function bindLockedNavNotice() {
  const lockedLinks = document.querySelectorAll("[data-locked-nav-link]");
  if (!lockedLinks.length) return;

  lockedLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      alert("로그인 후 이용 가능합니다.");
      window.location.href = "/login";
    });
  });
}

//DOM이 완전히 로드된 후에 실행됨
document.addEventListener("DOMContentLoaded", async () => {
  getSupabaseClient();
  bindApiActivityTracking();
  bindPasswordVisibilityToggles();
  loadRememberedLoginInfo();
  bindRememberLoginOption();
  bindGoogleOAuthButtons();
  bindForgotPasswordLink();
  try {
    const inRecoveryFlow = isPasswordRecoveryFlow();
    const hasSession = await syncInitialAuthState();
    if (inRecoveryFlow) {
      await maybeHandlePasswordRecoveryFlow();
    } else if (hasSession && window.location.pathname === OAUTH_LOGIN_PATH) {
      window.location.replace(OAUTH_POST_LOGIN_REDIRECT_PATH);
      return;
    }
  } catch (err) {
    console.error(err?.message || "초기 세션 동기화 중 오류가 발생했습니다.");
  }
  bindAuthForms();
  bindLogoutLink();
  bindLockedNavNotice();
  openSignUpPanelFromHash();
  bindIdleAutoLogout();
});

//외부에서 로그인,로그아웃 함수를 사용할 수 있도록 window 객체에 할당
window.supabaseAuth = {
  handleSignUp,
  handleSignIn,
  handleGoogleOAuth,
  handleForgotPassword,
  handleSignOut,
};
