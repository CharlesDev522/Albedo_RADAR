"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type NotificationSettings } from "@/lib/api";

function KindToggle({
  label,
  enabled,
  disabled,
  onChange,
}: {
  label: string;
  enabled: boolean;
  disabled: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between gap-3 py-1 text-[11px] text-zinc-300">
      <span className="min-w-0">{label}</span>
      <input
        type="checkbox"
        checked={enabled}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="rounded border-zinc-600 shrink-0"
      />
    </label>
  );
}

export default function NotificationSettingsPanel() {
  const [open, setOpen] = useState(false);
  const [settings, setSettings] = useState<NotificationSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getNotificationSettings(true);
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notification settings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open && !settings && !loading) {
      void load();
    }
  }, [open, settings, loading, load]);

  const patch = useCallback(
    async (patchBody: { notifications_enabled?: boolean; kinds?: Record<string, boolean> }) => {
      setSaving(true);
      setError(null);
      try {
        const data = await api.updateNotificationSettings(patchBody);
        setSettings(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to save notification settings");
      } finally {
        setSaving(false);
      }
    },
    []
  );

  const masterEnabled = settings?.notifications_enabled ?? false;
  const kindsDisabled = !masterEnabled || saving;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-[10px] transition-colors ${
          open
            ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
            : "border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
        }`}
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <span aria-hidden>🔔</span>
        Alerts
      </button>

      {open && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 cursor-default"
            aria-label="Close notification settings"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full mt-2 z-50 w-[min(92vw,22rem)] rounded-lg border border-zinc-700 bg-zinc-950 shadow-xl p-3 space-y-3">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="text-[12px] font-semibold text-zinc-100">Slack notifications</h2>
                <p className="text-[10px] text-zinc-500 mt-0.5">
                  Toggle which events post to Slack after the collector is live.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="text-zinc-500 hover:text-zinc-300 text-[11px]"
              >
                ✕
              </button>
            </div>

            {loading && !settings ? (
              <p className="text-[10px] text-zinc-500">Loading…</p>
            ) : settings ? (
              <>
                {!settings.webhook_configured && (
                  <p className="text-[10px] text-amber-300/90 border border-amber-500/20 bg-amber-500/5 rounded px-2 py-1.5">
                    Slack webhook is not configured — toggles are saved but nothing will post until
                    `SLACK_WEBHOOK_URL` is set.
                  </p>
                )}

                <label className="flex items-center justify-between gap-3 py-1 border-b border-zinc-800 pb-2 text-[11px] text-zinc-100 font-medium">
                  <span>All notifications</span>
                  <input
                    type="checkbox"
                    checked={masterEnabled}
                    disabled={saving || !settings.env_notifications_enabled}
                    onChange={(e) => void patch({ notifications_enabled: e.target.checked })}
                    className="rounded border-zinc-600"
                  />
                </label>

                {!settings.env_notifications_enabled && (
                  <p className="text-[10px] text-zinc-500">
                    `NOTIFICATIONS_ENABLED=false` in the environment — enable it to use Slack alerts.
                  </p>
                )}

                <div className="max-h-[50vh] overflow-y-auto space-y-3 pr-1">
                  {settings.groups.map((group) => (
                    <div key={group.id}>
                      <h3 className="text-[9px] uppercase tracking-wide text-zinc-500 mb-1">
                        {group.label}
                      </h3>
                      <div className="space-y-0.5">
                        {group.kinds.map((kind) => {
                          const row = settings.kinds[kind];
                          if (!row) return null;
                          return (
                            <KindToggle
                              key={kind}
                              label={row.label}
                              enabled={row.enabled}
                              disabled={kindsDisabled}
                              onChange={(next) => void patch({ kinds: { [kind]: next } })}
                            />
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>

                {settings.slack_channel && (
                  <p className="text-[9px] text-zinc-600">Channel: {settings.slack_channel}</p>
                )}
              </>
            ) : null}

            {error && <p className="text-[10px] text-rose-300">{error}</p>}

            <div className="flex items-center justify-between gap-2 pt-1 border-t border-zinc-800">
              <button
                type="button"
                onClick={() => void load()}
                disabled={loading || saving}
                className="text-[10px] text-zinc-400 hover:text-zinc-200 disabled:opacity-50"
              >
                Refresh
              </button>
              {saving && <span className="text-[10px] text-zinc-500">Saving…</span>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
