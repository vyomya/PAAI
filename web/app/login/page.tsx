"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** /login is kept as a stable URL; the landing page at / does the real work. */
export default function LoginPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
}
