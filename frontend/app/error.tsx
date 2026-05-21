"use client";

import { useEffect } from "react";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="min-h-screen bg-[#eef2f7] text-slate-900">
      <div className="flex min-h-screen items-center justify-center px-6">
        <div className="max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <h1 className="text-lg font-bold text-slate-900">화면을 불러오지 못했습니다.</h1>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            일시적인 오류가 발생했습니다. 새로고침 후 다시 시도해 주세요.
          </p>
          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={reset}
              className="rounded-lg border border-slate-300 bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
            >
              다시 시도
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}