export const restrictedContentMessage =
  "内容可能含证件/账户号码或登录凭据，本次未保存或发送给模型。请移除受限信息后重试；需要填写时由你在目标网站直接输入。";

export async function isRestrictedResponse(response: Response): Promise<boolean> {
  try {
    const payload: unknown = await response.clone().json();
    return typeof payload === "object" && payload !== null &&
      "error" in payload && typeof payload.error === "object" && payload.error !== null &&
      "code" in payload.error && payload.error.code === "restricted_content";
  } catch (error) {
    if (!(error instanceof SyntaxError || error instanceof TypeError || error instanceof DOMException)) throw error;
    return false;
  }
}
