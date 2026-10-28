import { redirect } from "next/navigation";

/** The old page now opens as a sheet over «Alle indstillinger». */
export default function Page() { redirect("/app/indstillinger?ark=webchat"); }
