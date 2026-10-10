import ReactMarkdown from "react-markdown";
import type { ChatMsg } from "../../types/agentforge";

function eventText(c: string): string {
  const m = c.match(/document_indexed filename=(\S+) chunks=(\d+)/);
  return m ? `Indexed ${m[1]} (${m[2]} sections)` : c.replace("SYSTEM_EVENT: ", "");
}

function getLangBadge(lang?: string, content?: string): string {
  if (lang) {
    if (lang === "ne") return "नेपाली";
    if (lang === "ne_roman") return "Roman";
    if (lang === "en") return "EN";
    if (lang === "mixed") return "Mixed";
  }
  // Fallback heuristic if language not set on msg
  if (content && /[\u0900-\u097F]/.test(content)) return "नेपाली";
  return "EN";
}

export default function ChatMessage({ msg, who }: { msg: ChatMsg; who: string }) {
  if (msg.role === "event") {
    return <p className="mx-auto my-1 w-fit rounded-full border border-rule bg-sheet px-3 py-1 text-xs text-ink-soft">{eventText(msg.content)}</p>;
  }
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded-lg bg-ink px-3.5 py-2 text-[15px] leading-snug text-sheet">
          {msg.content}
        </p>
      </div>
    );
  }
  const badge = getLangBadge(msg.language, msg.content);
  return (
    <div className="max-w-[92%]">
      <div className="mb-1 flex items-center gap-1.5">
        <p className="text-xs font-medium text-ink-soft">{who}</p>
        <span className="rounded bg-trace-wash px-1.5 py-0.2 text-[11px] font-semibold text-trace tracking-wide" title={`Language: ${badge}`}>
          {badge}
        </span>
      </div>
      <div className="font-serif text-[16.5px] leading-relaxed break-words [overflow-wrap:anywhere] [&_p+p]:mt-2 [&_ul]:list-disc [&_ul]:pl-5">
        <ReactMarkdown>{msg.content}</ReactMarkdown>
      </div>
    </div>
  );
}
