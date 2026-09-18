<#import "field.ftl" as field>
<#import "footer.ftl" as loginFooter>
<#macro username>
  <#assign label>
    <#if !realm.loginWithEmailAllowed>${msg("username")}<#elseif !realm.registrationEmailAsUsername>${msg("usernameOrEmail")}<#else>${msg("email")}</#if>
  </#assign>
  <@field.group name="username" label=label>
    <div class="${properties.kcInputGroup}">
      <div class="${properties.kcInputGroupItemClass} ${properties.kcFill}">
        <span class="${properties.kcInputClass} ${properties.kcFormReadOnlyClass}">
          <input id="kc-attempted-username" value="${auth.attemptedUsername}" readonly>
        </span>
      </div>
      <div class="${properties.kcInputGroupItemClass}">
        <button id="reset-login" class="${properties.kcFormPasswordVisibilityButtonClass} kc-login-tooltip" type="button" 
              aria-label="${msg('restartLoginTooltip')}" onclick="location.href='${url.loginRestartFlowUrl}'">
            <i class="fa-sync-alt fas" aria-hidden="true"></i>
            <span class="kc-tooltip-text">${msg("restartLoginTooltip")}</span>
        </button>
      </div>
    </div>
  </@field.group>
</#macro>

<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false>
<!DOCTYPE html>
<html class="${properties.kcHtmlClass!}" lang="${lang}"<#if realm.internationalizationEnabled> dir="${(locale.rtl)?then('rtl','ltr')}"</#if>>

<head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="color-scheme" content="light">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <#if properties.meta?has_content>
        <#list properties.meta?split(' ') as meta>
            <meta name="${meta?split('==')[0]}" content="${meta?split('==')[1]}"/>
        </#list>
    </#if>
    <title>${title!}</title>
    <link rel="icon" href="${url.resourcesPath}/img/favicon.ico" />
    <#if properties.stylesCommon?has_content>
        <#list properties.stylesCommon?split(' ') as style>
            <link href="${url.resourcesCommonPath}/${style}" rel="stylesheet" />
        </#list>
    </#if>
    <#if properties.styles?has_content>
        <#list properties.styles?split(' ') as style>
            <link href="${url.resourcesPath}/${style}" rel="stylesheet" />
        </#list>
    </#if>
    
    <style>
:root {
  --kc-primary: #0f172a;
  --kc-primary-hover: #1e293b;
  --kc-accent: #4f46e5;
  --kc-accent-glow: rgba(79, 70, 229, 0.15);
  --kc-text-main: #0f172a;
  --kc-text-muted: #64748b;
  --kc-border: #e2e8f0;
}

* {
  box-sizing: border-box !important;
}

html, body {
  margin: 0 !important;
  padding: 0 !important;
  min-height: 100vh !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif !important;
  background: radial-gradient(circle at 50% 10%, #1e1b4b 0%, #0f172a 45%, #020617 100%) !important;
  background-color: #090d16 !important;
  color: var(--kc-text-main) !important;
  -webkit-font-smoothing: antialiased !important;
  overflow-x: hidden !important;
}

/* Atmospheric ambient glow behind card */
body::before {
  content: "";
  position: fixed;
  top: 8%;
  left: 50%;
  transform: translateX(-50%);
  width: 680px;
  height: 500px;
  background: radial-gradient(ellipse at center, rgba(99, 102, 241, 0.22) 0%, rgba(59, 130, 246, 0.1) 45%, transparent 70%);
  pointer-events: none;
  z-index: 0;
}

#keycloak-bg {
  background: transparent !important;
  background-image: none !important;
}

/* Complete Override of PatternFly Multi-column Grid Across All Breakpoints */
@media (min-width: 0px) {
  .pf-v5-c-login,
  div.pf-v5-c-login {
    min-height: 100vh !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 2.5rem 1.25rem !important;
    position: relative !important;
    z-index: 1 !important;
  }

  .pf-v5-c-login__container,
  div.pf-v5-c-login__container {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
    max-width: 480px !important;
    margin: 0 auto !important;
    grid-template-columns: none !important;
    grid-template-rows: none !important;
    grid-template-areas: none !important;
    grid-area: auto !important;
  }

  .pf-v5-c-login__header,
  header#kc-header {
    grid-area: auto !important;
    width: 100% !important;
    max-width: 480px !important;
    margin: 0 0 1.5rem 0 !important;
    padding: 0 !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    text-align: center !important;
  }

  .pf-v5-c-brand,
  #kc-header-wrapper {
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    text-align: center !important;
    width: 100% !important;
  }

  .pf-v5-c-login__main,
  main.pf-v5-c-login__main {
    grid-area: auto !important;
    width: 100% !important;
    max-width: 480px !important;
    margin: 0 auto !important;
    background: #ffffff !important;
    border-radius: 1.5rem !important; /* 24px */
    box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.65), 0 0 0 1px rgba(255, 255, 255, 0.1) !important;
    border: 1px solid rgba(226, 232, 240, 0.8) !important;
    padding: 2.25rem 2.25rem 1.75rem 2.25rem !important;
    height: auto !important;
    min-height: 0 !important;
    flex-grow: 0 !important;
    display: flex !important;
    flex-direction: column !important;
  }

  /* Reset PatternFly's 48px body padding */
  .pf-v5-c-login__main-body,
  #kc-form,
  #kc-form-wrapper {
    height: auto !important;
    min-height: 0 !important;
    flex-grow: 0 !important;
    display: block !important;
    padding: 0 !important;
    margin: 0 !important;
  }
}

/* Brand Emblem & Typography */
.kc-brand-emblem-wrap {
  display: flex !important;
  justify-content: center !important;
  margin-bottom: 0.85rem !important;
}

.kc-brand-emblem {
  width: 58px !important;
  height: 58px !important;
  border-radius: 18px !important;
  background: linear-gradient(135deg, #6366f1 0%, #3b82f6 50%, #0ea5e9 100%) !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  color: #ffffff !important;
  box-shadow: 0 14px 28px -4px rgba(99, 102, 241, 0.5), 0 0 0 1.5px rgba(255, 255, 255, 0.25) inset !important;
}

.kc-brand-org-badge {
  display: inline-flex !important;
  align-items: center !important;
  gap: 0.4rem !important;
  padding: 0.35rem 0.95rem !important;
  border-radius: 9999px !important;
  background: rgba(255, 255, 255, 0.08) !important;
  border: 1px solid rgba(255, 255, 255, 0.15) !important;
  backdrop-filter: blur(8px) !important;
  font-size: 0.7rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.1em !important;
  color: #cbd5e1 !important;
  text-transform: uppercase !important;
  margin-bottom: 0.45rem !important;
  white-space: nowrap !important;
}

.kc-brand-app {
  font-size: 1.65rem !important;
  font-weight: 800 !important;
  letter-spacing: -0.025em !important;
  color: #ffffff !important;
  white-space: nowrap !important;
  text-align: center !important;
  text-shadow: 0 3px 15px rgba(0, 0, 0, 0.6) !important;
  margin: 0 !important;
}

/* Card Header */
.pf-v5-c-login__main-header {
  border-bottom: 1px solid #f1f5f9 !important;
  padding: 0 0 1.15rem 0 !important;
  margin: 0 0 1.35rem 0 !important;
  text-align: center !important;
  display: block !important;
}

#kc-page-title, .pf-v5-c-title {
  font-size: 1.35rem !important;
  font-weight: 800 !important;
  color: #0f172a !important;
  letter-spacing: -0.02em !important;
  margin: 0 0 0.35rem 0 !important;
  line-height: 1.3 !important;
  white-space: nowrap !important;
}

.kc-header-desc {
  font-size: 0.825rem !important;
  color: #64748b !important;
  margin: 0 !important;
  line-height: 1.45 !important;
}

.pf-v5-c-login__main-header-utilities {
  display: none !important;
}

/* Form Groups */
.pf-v5-c-form__group {
  margin-bottom: 1.15rem !important;
}

.pf-v5-c-form__group-label {
  padding-bottom: 0.35rem !important;
  text-align: left !important;
}

.pf-v5-c-form__label-text {
  font-size: 0.8125rem !important;
  font-weight: 700 !important;
  color: #334155 !important;
  letter-spacing: 0.01em !important;
}

/* Neutralize PatternFly pseudo-elements (removes the ugly blue underline) */
.pf-v5-c-form-control::before,
.pf-v5-c-form-control::after,
.pf-v5-c-input-group::before,
.pf-v5-c-input-group::after {
  display: none !important;
  content: none !important;
  border: none !important;
}

.pf-v5-c-form-control,
span.pf-v5-c-form-control {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
  display: block !important;
  width: 100% !important;
}

/* Single clean border on inputs */
.pf-v5-c-form__group input:not([type="checkbox"]):not([type="submit"]) {
  border-radius: 0.75rem !important; /* 12px */
  border: 1.5px solid #cbd5e1 !important;
  padding: 0 0.95rem !important;
  height: 48px !important;
  font-size: 0.875rem !important;
  color: #0f172a !important;
  background-color: #f8fafc !important;
  box-shadow: none !important;
  width: 100% !important;
  transition: all 0.15s ease-in-out !important;
  outline: none !important;
}

.pf-v5-c-form__group input:not([type="checkbox"]):not([type="submit"]):focus {
  background-color: #ffffff !important;
  border-color: #4f46e5 !important;
  box-shadow: 0 0 0 3px var(--kc-accent-glow) !important;
}

/* Password Input Group */
.pf-v5-c-input-group {
  display: flex !important;
  width: 100% !important;
  height: 48px !important;
  border-radius: 0.75rem !important;
  border: 1.5px solid #cbd5e1 !important;
  background-color: #f8fafc !important;
  overflow: hidden !important;
  transition: all 0.15s ease-in-out !important;
}

.pf-v5-c-input-group:focus-within {
  border-color: #4f46e5 !important;
  background-color: #ffffff !important;
  box-shadow: 0 0 0 3px var(--kc-accent-glow) !important;
}

.pf-v5-c-input-group .pf-v5-c-input-group__item.pf-m-fill {
  flex: 1 1 auto !important;
  display: flex !important;
  height: 100% !important;
}

.pf-v5-c-input-group input {
  border: none !important;
  border-radius: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  height: 100% !important;
  padding: 0 0.95rem !important;
  width: 100% !important;
}

.pf-v5-c-input-group input:focus {
  box-shadow: none !important;
}

.pf-v5-c-input-group .pf-v5-c-button.pf-m-control {
  background: transparent !important;
  border: none !important;
  color: #94a3b8 !important;
  padding: 0 0.95rem !important;
  cursor: pointer !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  height: 100% !important;
  transition: color 0.15s ease !important;
}

.pf-v5-c-input-group .pf-v5-c-button.pf-m-control:hover {
  color: #0f172a !important;
}

/* Checkbox */
.pf-v5-c-check {
  display: flex !important;
  align-items: center !important;
  gap: 0.5rem !important;
  margin: 0.5rem 0 1.15rem 0 !important;
}

.pf-v5-c-check__input {
  accent-color: #4f46e5 !important;
  width: 1rem !important;
  height: 1rem !important;
  cursor: pointer !important;
}

.pf-v5-c-check__label {
  font-size: 0.8125rem !important;
  font-weight: 500 !important;
  color: #475569 !important;
  cursor: pointer !important;
  user-select: none !important;
}

/* Primary Action Buttons */
.pf-v5-c-button.pf-m-primary,
#kc-login,
#kc-submit,
input[type="submit"] {
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%) !important;
  border: 1px solid #0f172a !important;
  color: #ffffff !important;
  border-radius: 0.75rem !important;
  padding: 0 !important;
  height: 48px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  font-size: 0.9375rem !important;
  font-weight: 700 !important;
  letter-spacing: 0.02em !important;
  width: 100% !important;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.25) !important;
  transition: all 0.15s ease-in-out !important;
  cursor: pointer !important;
  margin-top: 0.5rem !important;
}

.pf-v5-c-button.pf-m-primary:hover,
#kc-login:hover,
#kc-submit:hover {
  background: linear-gradient(135deg, #1e293b 0%, #334155 100%) !important;
  border-color: #1e293b !important;
  transform: translateY(-1.5px) !important;
  box-shadow: 0 8px 24px -4px rgba(15, 23, 42, 0.4) !important;
}

.pf-v5-c-button.pf-m-primary:active,
#kc-login:active,
#kc-submit:active {
  transform: translateY(0) !important;
}

.pf-v5-c-button.pf-m-secondary,
#kc-cancel {
  background-color: #f1f5f9 !important;
  border: 1px solid #e2e8f0 !important;
  color: #475569 !important;
  border-radius: 0.75rem !important;
  height: 48px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  font-size: 0.875rem !important;
  font-weight: 600 !important;
  width: 100% !important;
  cursor: pointer !important;
  margin-top: 0.5rem !important;
  transition: all 0.15s ease !important;
}

.pf-v5-c-button.pf-m-secondary:hover,
#kc-cancel:hover {
  background-color: #e2e8f0 !important;
  color: #0f172a !important;
}

/* Custom Alert Banner */
.kc-alert {
  display: flex !important;
  align-items: flex-start !important;
  gap: 0.625rem !important;
  padding: 0.75rem 1rem !important;
  border-radius: 0.75rem !important;
  font-size: 0.8125rem !important;
  line-height: 1.4 !important;
  margin-bottom: 1.15rem !important;
}

.kc-alert-icon {
  flex-shrink: 0 !important;
  margin-top: 1px !important;
}

.kc-alert-warning, .kc-alert-info {
  background-color: #eff6ff !important;
  border: 1px solid #bfdbfe !important;
  color: #1e40af !important;
}

.kc-alert-error, .kc-alert-danger {
  background-color: #fef2f2 !important;
  border: 1px solid #fecaca !important;
  color: #991b1b !important;
}

.kc-alert-success {
  background-color: #f0fdf4 !important;
  border: 1px solid #bbf7d0 !important;
  color: #166534 !important;
}

/* Security Footer inside Card (Zero dead space) */
.kc-card-security-footer {
  margin-top: 1.25rem !important;
  padding-top: 1rem !important;
  border-top: 1px solid #f1f5f9 !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  gap: 0.45rem !important;
  font-size: 0.725rem !important;
  color: #94a3b8 !important;
  font-weight: 500 !important;
}

/* Hide clutter */
.subtitle,
.pf-v5-c-form__helper-text:empty,
.pf-v5-c-login__main-footer:empty,
#kc-info {
  display: none !important;
}
    </style>

    <script type="importmap">
        {
            "imports": {
                "rfc4648": "${url.resourcesCommonPath}/vendor/rfc4648/rfc4648.js"
            }
        }
    </script>
    <#if properties.scripts?has_content>
        <#list properties.scripts?split(' ') as script>
            <script src="${url.resourcesPath}/${script}" type="text/javascript"></script>
        </#list>
    </#if>
    <#if scripts??>
        <#list scripts as script>
            <script src="${script}" type="text/javascript"></script>
        </#list>
    </#if>
    <script type="module" src="${url.resourcesPath}/js/passwordVisibility.js"></script>
    <script type="module">
        <#outputformat "JavaScript">
        import { startSessionPolling } from ${(url.resourcesPath + "/js/authChecker.js")?c};

        startSessionPolling(
            ${url.ssoLoginInOtherTabsUrl?c}
        );
        </#outputformat>
    </script>
    <script type="module">
        document.addEventListener("click", (event) => {
            const link = event.target.closest("a[data-once-link]");

            if (!link) {
                return;
            }

            if (link.getAttribute("aria-disabled") === "true") {
                event.preventDefault();
                return;
            }

            const { disabledClass } = link.dataset;

            if (disabledClass) {
                link.classList.add(...disabledClass.trim().split(/\s+/));
            }

            link.setAttribute("role", "link");
            link.setAttribute("aria-disabled", "true");
        });
    </script>
    <#if authenticationSession??>
        <script type="module">
             <#outputformat "JavaScript">
            import { checkAuthSession } from ${(url.resourcesPath + "/js/authChecker.js")?c};

            checkAuthSession(
                ${authenticationSession.authSessionIdHash?c}
            );
            </#outputformat>
        </script>
    </#if>
</head>

<body id="keycloak-bg" class="${properties.kcBodyClass!}" data-page-id="login-${pageId}">
<div class="pf-v5-c-login">
  <div class="pf-v5-c-login__container">
    <header id="kc-header" class="pf-v5-c-login__header">
      <div id="kc-header-wrapper" class="pf-v5-c-brand">
        <div class="kc-brand-emblem-wrap">
          <div class="kc-brand-emblem">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>
              <polyline points="2 17 12 22 22 17"></polyline>
              <polyline points="2 12 12 17 22 12"></polyline>
            </svg>
          </div>
        </div>
        <div class="kc-brand-org-badge">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          <span>HỆ THỐNG QUẢN LÝ DỮ LIỆU ĐỊA CHÍNH</span>
        </div>
        <h1 class="kc-brand-app">OCR SỔ ĐỎ &amp; SỔ HỒNG</h1>
      </div>
    </header>

    <main class="pf-v5-c-login__main">
      <div class="pf-v5-c-login__main-header">
        <h2 class="pf-v5-c-title" id="kc-page-title"><#nested "header"></h2>
        <p class="kc-header-desc">
          <#if pageId == "login">
            Nhập thông tin tài khoản được cấp để truy cập hệ thống
          <#elseif pageId == "login-update-password">
            Vui lòng đặt mật khẩu mới để kích hoạt và bảo mật tài khoản
          <#elseif pageId == "login-reset-password">
            Nhập thông tin để khôi phục mật khẩu tài khoản
          <#else>
            Hệ thống xác thực tập trung an toàn
          </#if>
        </p>
      </div>

      <div class="pf-v5-c-login__main-body">
        <#-- Message banner -->
        <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
            <div class="kc-alert kc-alert-${(message.type = 'error')?then('danger', message.type)}">
                <div class="kc-alert-icon">
                    <#if message.type = 'success'>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>
                    <#elseif message.type = 'warning'>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                    <#elseif message.type = 'error'>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                    <#else>
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                    </#if>
                </div>
                <span class="kc-alert-text">${message.summary}</span>
            </div>
        </#if>

        <#nested "form">

        <#if auth?has_content && auth.showTryAnotherWayLink()>
          <form id="kc-select-try-another-way-form" action="${url.loginAction}" method="post" novalidate="novalidate">
              <input type="hidden" name="tryAnotherWay" value="on"/>
              <a id="try-another-way" href="javascript:document.forms['kc-select-try-another-way-form'].requestSubmit()"
                  class="${properties.kcButtonSecondaryClass} ${properties.kcButtonBlockClass} ${properties.kcMarginTopClass}">
                    ${msg("doTryAnotherWay")}
              </a>
          </form>
        </#if>

        <div class="kc-card-security-footer">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
          </svg>
          <span>Kết nối bảo mật chuẩn xác thực OpenID Connect</span>
        </div>
      </div>
    </main>
  </div>
</div>
</body>
</html>
</#macro>