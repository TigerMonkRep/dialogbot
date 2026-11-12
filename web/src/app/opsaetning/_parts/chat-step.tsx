"use client";
import { useCallback, useState } from "react";
import { ChatSetup, type Webchat } from "./channels";
import { StepFooter } from "./footer";

/** The Chat step's content and its «Videre», which saves the domain and greeting first when they were changed. */
export function ChatStep({ wsId, w, canManage, website, company, nextHref, nextLabel, status }: { wsId: string; w: Webchat; canManage: boolean; website: string; company: string; nextHref: string; nextLabel: string; status: string }) {
  const [save, setSave] = useState<(() => Promise<boolean>) | null>(null);
  const onDirty = useCallback((fn: (() => Promise<boolean>) | null) => setSave(() => fn), []);
  return (
    <div className="flex flex-col gap-6">
      <ChatSetup wsId={wsId} w={w} canManage={canManage} website={website} company={company} onDirty={onDirty} />
      <StepFooter href={nextHref} label={nextLabel} status={status} before={save} />
    </div>
  );
}
