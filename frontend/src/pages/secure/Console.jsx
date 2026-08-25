import RetrainPanel from "../../components/model/RetrainPanel";
import SecurityCard from "../../components/secure/SecurityCard";
import DataActions from "../../components/secure/DataActions";
import DataProvenance from "../../components/DataProvenance";
import useAuth from "../../hooks/useAuth";
import { C, radius, space, type } from "../../theme";

/* Operator controls, separated from the public site.
 *
 * Everything here changes the model or the data, which is why it is behind a
 * login: an open retrain button is a denial-of-service control on a 0.1 vCPU
 * instance, and an open refresh is a way to churn the database.
 *
 * The public Model page keeps the metrics, calibration and baselines — those are
 * the numbers that let a visitor judge the model, and hiding them would make the
 * app less honest, not more secure. */
export default function Console() {
  const { username, logout } = useAuth();

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: space.sm, marginBottom: space.lg }}>
        <div>
          <div style={{ ...type.page, color: C.navy }}>Model operations</div>
          <div style={{ ...type.body, color: C.slate500 }}>
            Signed in as <strong>{username}</strong>
          </div>
        </div>
        <button onClick={logout} style={{
          padding: "7px 14px", borderRadius: radius.sm, border: `1px solid ${C.slate200}`,
          background: C.white, color: C.slate600, ...type.label, cursor: "pointer",
        }}>
          Sign out
        </button>
      </div>

      <div style={{ marginBottom: space.lg }}>
        <RetrainPanel />
      </div>

      <div style={{ marginBottom: space.lg }}>
        <DataActions />
      </div>

      <div style={{ marginBottom: space.lg }}>
        <SecurityCard />
      </div>

      <DataProvenance />
    </div>
  );
}
