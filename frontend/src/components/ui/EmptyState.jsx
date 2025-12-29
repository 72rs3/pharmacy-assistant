export default function EmptyState({ title, description, actions = null }) {
  return (
    <div className="empty-state">
      <div className="empty-state-inner">
        <h3 className="empty-state-title">{title}</h3>
        {description ? <p className="empty-state-description">{description}</p> : null}
        {actions ? <div className="empty-state-actions">{actions}</div> : null}
      </div>
    </div>
  );
}

