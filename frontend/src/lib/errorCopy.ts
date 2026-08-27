import type { ErrorCode } from "./api/errors";

/**
 * Pure code -> copy map, no logic. Maps every backend error envelope code to
 * plain-language copy in English and Hindi. Never show the bare code to an
 * end user -- a `request_id` may be shown small for support, nothing else.
 */
export interface ErrorCopyEntry {
  title: string;
  description: string;
  action?: string;
}

export type ErrorCopyLanguage = "en" | "hi";

const en: Record<ErrorCode, ErrorCopyEntry> = {
  'AUTH_INVALID_CREDENTIALS': {
    title: "Incorrect email or password",
    description: "Double-check your details and try again.",
    action: "Try again",
  },
  'AUTH_TOKEN_EXPIRED': {
    title: "Your session expired",
    description: "For your security, please log in again to continue.",
    action: "Log in",
  },
  'AUTH_FORBIDDEN': {
    title: "You don't have access to this",
    description: "This account doesn't have permission to view or change this record.",
  },
  'CAPTCHA_REQUIRED': {
    title: "Verification needed",
    description: "Please complete the quick verification step to continue.",
    action: "Verify",
  },
  'CAPTCHA_INVALID': {
    title: "Verification didn't go through",
    description: "That attempt failed. Please try the verification again.",
    action: "Retry",
  },
  'VALIDATION_FAILED': {
    title: "Some details need fixing",
    description: "Please check the highlighted fields and try again.",
  },
  'NOT_FOUND': {
    title: "We couldn't find that",
    description: "This record may have been moved, or the link may be out of date.",
  },
  'LOCKED': {
    title: "This record is locked",
    description: "It's already been approved and signed, so it can't be edited. Create an amendment instead.",
  },
  'CONFLICT': {
    title: "This changed while you were looking",
    description: "Someone else may have updated this. Please refresh and try again.",
    action: "Refresh",
  },
  'RATE_LIMITED': {
    title: "Too many attempts",
    description: "Please wait a short while before trying again.",
  },
  'UPSTREAM_UNAVAILABLE': {
    title: "Connection is a little unstable",
    description: "Your report has already been saved and will keep processing once the connection improves. You don't need to re-upload it.",
    action: "Retry now",
  },
  'MODEL_UNAVAILABLE': {
    title: "AI assistance is briefly unavailable",
    description: "Your information is safely saved. The clinical brief will be ready shortly — no action is needed from you.",
    action: "Retry now",
  },
  'INTERNAL': {
    title: "Something went wrong on our end",
    description: "Please try again in a moment. If this keeps happening, contact your clinic.",
  },
  'NOT_IMPLEMENTED': {
    title: "Not available yet",
    description: "This feature is still being built and isn't ready to use.",
  },
};

const hi: Record<ErrorCode, ErrorCopyEntry> = {
  'AUTH_INVALID_CREDENTIALS': {
    title: "गलत ईमेल या पासवर्ड",
    description: "कृपया अपनी जानकारी जांचें और फिर से कोशिश करें।",
    action: "फिर से कोशिश करें",
  },
  'AUTH_TOKEN_EXPIRED': {
    title: "आपका सत्र समाप्त हो गया",
    description: "सुरक्षा कारणों से, कृपया फिर से लॉग इन करें।",
    action: "लॉग इन करें",
  },
  'AUTH_FORBIDDEN': {
    title: "आपको इसकी अनुमति नहीं है",
    description: "इस खाते को यह रिकॉर्ड देखने या बदलने की अनुमति नहीं है।",
  },
  'CAPTCHA_REQUIRED': {
    title: "सत्यापन आवश्यक है",
    description: "जारी रखने के लिए कृपया त्वरित सत्यापन पूरा करें।",
    action: "सत्यापित करें",
  },
  'CAPTCHA_INVALID': {
    title: "सत्यापन पूरा नहीं हुआ",
    description: "वह प्रयास विफल रहा। कृपया सत्यापन फिर से करें।",
    action: "फिर से कोशिश करें",
  },
  'VALIDATION_FAILED': {
    title: "कुछ विवरण ठीक करने होंगे",
    description: "कृपया हाइलाइट किए गए फ़ील्ड जांचें और फिर से कोशिश करें।",
  },
  'NOT_FOUND': {
    title: "हमें वह नहीं मिला",
    description: "यह रिकॉर्ड स्थानांतरित हो गया होगा, या लिंक पुराना हो सकता है।",
  },
  'LOCKED': {
    title: "यह रिकॉर्ड लॉक है",
    description: "यह पहले ही स्वीकृत और हस्ताक्षरित हो चुका है, इसलिए संपादित नहीं किया जा सकता। इसके बजाय एक संशोधन बनाएं।",
  },
  'CONFLICT': {
    title: "यह अभी-अभी बदला है",
    description: "किसी और ने इसे अपडेट किया होगा। कृपया रीफ्रेश करें और फिर से कोशिश करें।",
    action: "रीफ्रेश करें",
  },
  'RATE_LIMITED': {
    title: "बहुत अधिक प्रयास",
    description: "कृपया कुछ देर प्रतीक्षा करने के बाद फिर से कोशिश करें।",
  },
  'UPSTREAM_UNAVAILABLE': {
    title: "कनेक्शन थोड़ा अस्थिर है",
    description: "आपकी रिपोर्ट पहले ही सहेजी जा चुकी है और कनेक्शन बेहतर होते ही प्रोसेस होती रहेगी। दोबारा अपलोड करने की जरूरत नहीं है।",
    action: "अभी फिर कोशिश करें",
  },
  'MODEL_UNAVAILABLE': {
    title: "एआई सहायता थोड़ी देर के लिए अनुपलब्ध है",
    description: "आपकी जानकारी सुरक्षित रूप से सहेजी गई है। क्लिनिकल ब्रीफ जल्द ही तैयार हो जाएगी — आपको कुछ करने की जरूरत नहीं है।",
    action: "अभी फिर कोशिश करें",
  },
  'INTERNAL': {
    title: "हमारी ओर से कुछ गड़बड़ हुई",
    description: "कृपया कुछ देर बाद फिर से कोशिश करें। यदि यह बार-बार हो, तो अपने क्लिनिक से संपर्क करें।",
  },
  'NOT_IMPLEMENTED': {
    title: "अभी उपलब्ध नहीं है",
    description: "यह सुविधा अभी बन रही है और उपयोग के लिए तैयार नहीं है।",
  },
};

const tables: Record<ErrorCopyLanguage, Record<ErrorCode, ErrorCopyEntry>> = { en, hi };

export function getErrorCopy(code: ErrorCode, lang: ErrorCopyLanguage = "en"): ErrorCopyEntry {
  return tables[lang][code] ?? tables[lang].INTERNAL;
}
