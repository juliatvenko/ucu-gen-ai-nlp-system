export async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Request failed (${response.status})`);
  return response.json();
}

/** POST and read server-sent events. Rejects if the stream ends without a result or reports an error. */
export async function postStream(
  url: string,
  body: unknown,
  onEvent: (event: string, data: any) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) throw new Error(`The server rejected the request (${response.status}).`);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const handle = (block: string) => {
    const event = block.match(/^event: (.*)$/m)?.[1];
    const data = block.match(/^data: (.*)$/m)?.[1];
    if (!event || !data) return;
    const parsed = JSON.parse(data);
    if (event === "error") throw new Error(parsed.message);
    if (event === "result") finished = true;
    onEvent(event, parsed);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    blocks.forEach(handle);
  }
  if (!finished) throw new Error("The connection ended before a result arrived. Please try again.");
}

/** Ranges of a quote in the patient text, matching the server's guard: whitespace and case don't matter. */
export function findQuote(text: string, quote: string): [number, number] | null {
  const words = quote.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return null;
  const pattern = words
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/['’‘]/g, "['’‘]").replace(/["“”]/g, '["“”]'))
    .join("\\s+");
  const match = new RegExp(pattern, "i").exec(text);
  return match ? [match.index, match.index + match[0].length] : null;
}
