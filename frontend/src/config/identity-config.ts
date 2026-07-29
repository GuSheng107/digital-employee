import {
  getCountryCallingCode,
  isSupportedCountry,
  type CountryCode,
} from 'libphonenumber-js';

const FALLBACK_PHONE_REGION: CountryCode = 'CN';

function resolvePhoneRegion(): CountryCode {
  const configuredRegion = import.meta.env.VITE_PHONE_DEFAULT_REGION
    ?.trim()
    .toUpperCase();
  if (configuredRegion && isSupportedCountry(configuredRegion)) {
    return configuredRegion;
  }
  return FALLBACK_PHONE_REGION;
}

/** 当前开放注册的号码地区；修改环境变量即可切换，不依赖硬编码号码段。 */
export const PHONE_DEFAULT_REGION = resolvePhoneRegion();

/** 当前地区国际区号，供表单前缀展示。 */
export const PHONE_DIAL_PREFIX =
  `+${getCountryCallingCode(PHONE_DEFAULT_REGION)}`;
