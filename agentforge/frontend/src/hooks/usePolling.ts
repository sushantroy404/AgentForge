import { useEffect, useState } from "react";
import { client } from "../api/client";
import type { JobRecord } from "../types/agentforge";

/** Polls a job once per second until it leaves the 'running' state. */
export function useJob(jobId: string | null) {
  const [job, setJob] = useState<JobRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setJob(null); setError(null);
    if (!jobId) return;
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const j = await client.job(jobId);
        if (stop) return;
        setJob(j);
        if (j.status === "running") timer = setTimeout(tick, 1000);
      } catch (e) {
        if (!stop) setError((e as Error).message);
      }
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [jobId]);
  return { job, error };
}
