export default function Table({ columns, rows, getRowKey }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} className={col.className ?? ""}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={getRowKey ? getRowKey(row) : idx}>
              {columns.map((col) => (
                <td key={col.key} className={col.className ?? ""}>
                  {typeof col.cell === "function" ? col.cell(row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

