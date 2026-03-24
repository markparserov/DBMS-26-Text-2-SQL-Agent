type Props = {
  sql: string;
};

export default function SqlBlock({ sql }: Props) {
  if (!sql) return null;
  return (
    <details className="sqlDetails">
      <summary>Показать SQL-запрос</summary>
      <pre className="sqlCode">
        <code>{sql}</code>
      </pre>
    </details>
  );
}
