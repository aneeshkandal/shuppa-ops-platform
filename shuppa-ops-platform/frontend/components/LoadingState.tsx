import Icon from "./Icon";

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return <div className="state-box loading-box">{label}</div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="state-box error-box">
      <strong>Couldn&apos;t load this.</strong>
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="btn-secondary btn-small" onClick={onRetry}>
          <Icon name="refreshCw" size={13} strokeWidth={2.2} /> Try again
        </button>
      )}
    </div>
  );
}
