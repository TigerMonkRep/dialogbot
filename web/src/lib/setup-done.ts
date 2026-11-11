/** Trin 1 is done with a name and «hvad I laver» – plus the number customers ring when Dialogbot takes the phone. A
 *  chat-only business needs no phone number (Fürster 11/11: webchat without a phone). Shared by the server (stepper,
 *  «I dag») and trin 1 itself (the «Videre» button), so both always agree. */
export const profileIsDone = (profile: { legal_name: string; description: string; phone: string | null }, wantsPhone: boolean) =>
  Boolean(profile.legal_name?.trim() && profile.description.trim() && (!wantsPhone || profile.phone?.trim()));
