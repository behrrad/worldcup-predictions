"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";

import { apiFetch } from "@/lib/api";

export default function JoinLeague() {
  const { getToken } = useAuth();
  const router = useRouter();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const token = await getToken();
      const res = await apiFetch("/leagues/join/", token, {
        method: "POST",
        body: JSON.stringify({ invite_code: code }),
      });
      router.push(`/l/${res.slug}`);
    } catch {
      setError("کد دعوت نامعتبر است.");
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <div className="field">
        <label>کد دعوت</label>
        <input
          className="input"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="مثلاً: ABCD2345"
          style={{ letterSpacing: ".2em" }}
          required
        />
        {error && <div className="help" style={{ color: "var(--danger)" }}>{error}</div>}
      </div>
      <button className="btn btn-pitch btn-block" type="submit" disabled={loading}>
        {loading ? "در حال پیوستن…" : "پیوستن"}
      </button>
    </form>
  );
}
