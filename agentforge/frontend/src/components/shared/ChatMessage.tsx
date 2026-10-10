import ReactMarkdown from "react-markdown";
import type { ChatMsg } from "../../types/agentforge";

function eventText(c: string): string {
  const m = c.match(/document_indexed filename=(\S+) chunks=(\d+)/);
  return m ? `Indexed ${m[1]} (${m[2]} sections)` : c.replace("SYSTEM_EVENT: ", "");
}

export default function ChatMessage({ msg, who }: { msg: ChatMsg; who: string }) {
  if (msg.role === "event") {
    return <p className="mx-auto my-1 w-fit rounded-full border border-rule bg-sheet px-3 py-1 text-xs text-ink-soft">{eventText(msg.content)}</p>;
  }
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-ink px-3.5 py-2 text-[15px] leading-snug text-sheet">{msg.content}</p>
      </div>
    );
  }
  return (
    <div className="max-w-[92%]">
      <p className="mb-0.5 text-xs font-medium text-ink-soft">{who}</p>
      <div className="font-serif text-[16.5px] leading-relaxed [&_p+p]:mt-2 [&_ul]:list-disc [&_ul]:pl-5">
        <ReactMarkdown>{msg.content}</ReactMarkdown>
      </div>
    </div>
  );
}
