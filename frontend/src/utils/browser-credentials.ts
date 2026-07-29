const REMEMBER_PASSWORD_PREFERENCE_KEY = 'remember_password_enabled';

interface PasswordCredentialData {
  id: string;
  password: string;
  name?: string;
}

declare global {
  interface PasswordCredential extends Credential {
    readonly password: string;
  }

  interface CredentialRequestOptions {
    password?: boolean;
  }

  var PasswordCredential: {
    prototype: PasswordCredential;
    new(data: PasswordCredentialData): PasswordCredential;
  };
}

export interface RememberedCredential {
  username: string;
  password: string;
}

/** 是否由用户主动启用了浏览器密码记忆。 */
export function isRememberPasswordEnabled(): boolean {
  return localStorage.getItem(REMEMBER_PASSWORD_PREFERENCE_KEY) === 'true';
}

/** 从浏览器内建凭据库读取已授权的密码，不从 Web Storage 读取明文。 */
export async function loadRememberedCredential(): Promise<RememberedCredential | null> {
  if (
    !isRememberPasswordEnabled()
    || typeof PasswordCredential === 'undefined'
  ) {
    return null;
  }
  try {
    const credential = await navigator.credentials.get({
      password: true,
      mediation: 'optional',
    });
    if (!(credential instanceof PasswordCredential)) {
      return null;
    }
    return {
      username: credential.id,
      password: credential.password,
    };
  } catch {
    return null;
  }
}

/** 将登录凭据交给浏览器密码管理器保存，应用自身不持久化明文密码。 */
export async function rememberCredential(
  username: string,
  password: string,
): Promise<void> {
  localStorage.setItem(REMEMBER_PASSWORD_PREFERENCE_KEY, 'true');
  if (typeof PasswordCredential === 'undefined') {
    return;
  }
  try {
    await navigator.credentials.store(
      new PasswordCredential({
        id: username,
        name: username,
        password,
      }),
    );
  } catch {
    // 浏览器拒绝或不支持保存时，仍由标准 autocomplete 接管。
  }
}

/** 关闭自动取用凭据；浏览器密码库中的删除由用户在浏览器内管理。 */
export async function forgetCredentialPreference(): Promise<void> {
  localStorage.removeItem(REMEMBER_PASSWORD_PREFERENCE_KEY);
  try {
    await navigator.credentials.preventSilentAccess();
  } catch {
    // 不支持凭据管理 API 的浏览器无需额外处理。
  }
}
