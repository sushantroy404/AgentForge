import { useEffect, useRef, useState, type ReactNode } from "react";
import { Send } from "lucide-react";
import type { ChatMsg } from "../../types/agentforge";
import ChatMessage from "./ChatMessage";

interface Props {
  who: string;
  messages: ChatMsg[];
  busy: boolean;
  error: string | null;
  placeholder: string;
  onSend: (text: string) => Promise<boolean>;
  prefill?: { text: string; n: number } | null;
  above?: ReactNode;
}

export default function ChatPanel({ who, messages, busy, error, placeholder, onSend, prefill, above }: Props) {
  const [text, setText] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => { if (prefill) setText(prefill.text); }, [prefill?.n]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages.length, busy]);
  useEffect(() => {
    if (!busy) { setElapsed(0); return; }
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);

  const submit = async () => {
    const t = text.trim();
    if (!t || busy) return;
    if (await onSend(t)) setText("");
  };

  return (
    <section className="flex h-full min-h-0 flex-col">
      <div className="scroll-thin flex-1 space-y-4 overflow-y-auto px-5 py-5" aria-live="polite">
        {messages.map((m, i) => <ChatMessage key={i} msg={m} who={who} />)}
        {busy && <p className="text-sm text-ink-soft">{who} is thinking… {elapsed > 0 && `${elapsed}s`}</p>}
        <div ref={end} />
      </div>
      {error && <p role="alert" className="mx-5 mb-2 rounded border border-stop bg-stop-wash px-3 py-2 text-sm text-stop">{error}</p>}
      <div className="border-t border-rule bg-sheet px-5 py-3">
        {above}
        <div className="flex items-end gap-2">
          <textarea
            value={text} onChange={(e) => setText(e.target.value)} rows={2} placeholder={placeholder}
            aria-label="Message"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
            className="min-h-[3rem] flex-1 resize-none rounded-md border border-rule bg-white px-3 py-2 text-[15px]"
          />
          <button onClick={submit} disabled={busy || !text.trim()} aria-label="Send message"
            className="flex h-12 w-12 items-center justify-center rounded-md bg-trace text-white disabled:opacity-40">
            <Send size={18} />
          </button>
        </div>
      </div>
    </section>
  );
}
