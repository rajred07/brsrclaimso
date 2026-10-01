"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

export default function FilingPageRedirect() {
  const params = useParams();
  const router = useRouter();
  const filingId = (params?.id as string) || "infosys-2022";

  useEffect(() => {
    router.replace(`/verify/${filingId}`);
  }, [filingId, router]);

  return (
    <div className="flex items-center justify-center min-h-[400px]">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[var(--primary)]"></div>
    </div>
  );
}
