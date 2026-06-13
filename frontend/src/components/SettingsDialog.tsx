import { useEffect, useState } from "react";
import { getComputeSettings, updateComputeSettings } from "../api";
import type { ComputeSettings } from "../types";

const GPU_TYPES = ["T4", "L4", "A10G", "A100", "H100"];

export function SettingsDialog({ onClose }: { onClose: () => void }) {
  const [settings, setSettings] = useState<ComputeSettings | null>(null);
  const [tokenId, setTokenId] = useState("");
  const [tokenSecret, setTokenSecret] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    getComputeSettings().then((s) => {
      setSettings(s);
      setTokenId(s.modal_token_id);
    });
  }, []);

  if (!settings) return null;

  async function save() {
    if (!settings) return;
    setStatus("saving…");
    try {
      const updated = await updateComputeSettings({
        compute_backend: settings.compute_backend,
        gpu_type: settings.gpu_type,
        // only send token fields the user actually edited; null keeps stored values
        modal_token_id: tokenId !== settings.modal_token_id ? tokenId : null,
        modal_token_secret: tokenSecret ? tokenSecret : null,
        gate_plan: settings.gate_plan,
        gate_training_jobs: settings.gate_training_jobs,
        gate_shell: settings.gate_shell,
      });
      setSettings(updated);
      setTokenSecret("");
      setStatus("saved ✓");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "save failed");
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <h2>Compute settings</h2>
        <p className="muted">
          Where <code>run_training_job</code> executes training and heavy compute.
        </p>

        <label className="field">
          <span>Backend</span>
          <div className="radio-row">
            <label>
              <input
                type="radio"
                checked={settings.compute_backend === "local"}
                onChange={() => setSettings({ ...settings, compute_backend: "local" })}
              />
              Local — this server's CPU/GPU
            </label>
            <label>
              <input
                type="radio"
                checked={settings.compute_backend === "modal"}
                onChange={() => setSettings({ ...settings, compute_backend: "modal" })}
              />
              Modal — remote GPU sandbox
            </label>
          </div>
        </label>

        {settings.compute_backend === "modal" && (
          <>
            <label className="field">
              <span>GPU type</span>
              <select
                value={settings.gpu_type}
                onChange={(e) => setSettings({ ...settings, gpu_type: e.target.value })}
              >
                {GPU_TYPES.map((g) => (
                  <option key={g}>{g}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Modal token ID</span>
              <input
                value={tokenId}
                placeholder="ak-..."
                onChange={(e) => setTokenId(e.target.value)}
              />
            </label>
            <label className="field">
              <span>
                Modal token secret{" "}
                {settings.modal_token_secret_set && (
                  <em className="muted">(saved — leave blank to keep)</em>
                )}
              </span>
              <input
                type="password"
                value={tokenSecret}
                placeholder={settings.modal_token_secret_set ? "••••••••" : "as-..."}
                onChange={(e) => setTokenSecret(e.target.value)}
              />
            </label>
            <p className="muted">
              Create a token at modal.com → Settings → API Tokens. Jobs upload your
              script + data, run on the selected GPU, and download <code>outputs/</code>{" "}
              back to your workspace.
            </p>
          </>
        )}

        <h2 className="section-heading">Approval gates</h2>
        <p className="muted">Pause for your approval before the agent takes these actions.</p>
        <label className="check-row">
          <input
            type="checkbox"
            checked={settings.gate_plan}
            onChange={(e) => setSettings({ ...settings, gate_plan: e.target.checked })}
          />
          Review the research plan before experiments
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={settings.gate_training_jobs}
            onChange={(e) => setSettings({ ...settings, gate_training_jobs: e.target.checked })}
          />
          Approve training jobs before they run (they can cost money)
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={settings.gate_shell}
            onChange={(e) => setSettings({ ...settings, gate_shell: e.target.checked })}
          />
          Approve shell commands before they run
        </label>

        <div className="dialog-actions">
          <span className="muted">{status}</span>
          <button className="ghost" onClick={onClose}>
            Close
          </button>
          <button className="primary" onClick={save}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
