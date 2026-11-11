import { expect } from "@playwright/test";
import { appSuite } from "./app-suite";
import { api, chat } from "./pb-helpers";

/** Pakkeliste (PC-APP-PAKKELISTE-01..05). No settings panel (coverage §3.9); the list is a task in Opgaver. */
const SEED = "Lav en pakkeliste til en uge i sommerhus med badetøj, solcreme og bøger";

appSuite({
  key: "pakkeliste", sid: "PC-APP-PAKKELISTE", plans: "plus", seed: SEED, probe: "/addons", probeGated: false, deletable: true,
  proveSeed: async (page) => {
    const out = await chat(page, SEED);
    const tid = out.messages.find((m) => m.kind === "task")!.task_id!;
    const t = await (await api(page, "GET", `/tasks/${tid}`)).json();
    expect(t.items.map((i: { text: string }) => i.text)).toEqual(["Badetøj", "Solcreme", "Bøger"]);
    const out2 = await chat(page, "Lav en pakkeliste som sidst");
    const tid2 = out2.messages.find((m) => m.kind === "task")!.task_id!;
    expect(tid2).not.toBe(tid);
    const t2 = await (await api(page, "GET", `/tasks/${tid2}`)).json();
    expect(t2.items.map((i: { text: string }) => i.text)).toEqual(["Badetøj", "Solcreme", "Bøger"]);
  },
  panelText: null,
});
