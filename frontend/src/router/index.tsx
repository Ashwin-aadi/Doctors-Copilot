import { Suspense, lazy, type ComponentType } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { RootLayout } from "../app/RootLayout";
import { NotFound } from "../app/NotFound";
import { Skeleton } from "../components/ui/Skeleton";
import { ProtectedRoute } from "./ProtectedRoute";
import { GuestRoute } from "./GuestRoute";
import { ROUTES, PATIENT_ROLES, DOCTOR_STAFF_ROLES, CLINICAL_ROLES } from "./routes";

const isDev = import.meta.env.DEV;

/**
 * Every screen is loaded on demand.
 *
 * Bundled eagerly, the whole product shipped on first paint -- a doctor
 * opening the login page downloaded the upload pipeline, the OCR review
 * editor and the charting libraries before typing a password. Each route is
 * its own chunk now, so first paint carries the shell and the screen actually
 * asked for; the rest arrives while the user is reading.
 *
 * The containers are named exports, hence the `.then` unwrap.
 */
function route<T extends Record<string, unknown>, K extends keyof T>(
  loader: () => Promise<T>,
  name: K,
) {
  return lazy(async () => ({ default: (await loader())[name] as ComponentType }));
}

const LoginContainer = route(() => import("../features/auth/LoginContainer"), "LoginContainer");
const RegisterContainer = route(
  () => import("../features/auth/RegisterContainer"),
  "RegisterContainer",
);
const ForgotPasswordContainer = route(
  () => import("../features/auth/ForgotPasswordContainer"),
  "ForgotPasswordContainer",
);
const ResetPasswordContainer = route(
  () => import("../features/auth/ResetPasswordContainer"),
  "ResetPasswordContainer",
);
const OnboardingContainer = route(
  () => import("../features/onboarding/OnboardingContainer"),
  "OnboardingContainer",
);
const TriageContainer = route(
  () => import("../features/triage/TriageContainer"),
  "TriageContainer",
);
const ChatbotContainer = route(
  () => import("../features/chatbot/ChatbotContainer"),
  "ChatbotContainer",
);
const BookingContainer = route(
  () => import("../features/booking/BookingContainer"),
  "BookingContainer",
);
const VisitListContainer = route(
  () => import("../features/visits/VisitListContainer"),
  "VisitListContainer",
);
const VisitContainer = route(() => import("../features/visit/VisitContainer"), "VisitContainer");
const QueueBoardContainer = route(
  () => import("../features/queue/QueueBoardContainer"),
  "QueueBoardContainer",
);
const UploadContainer = route(
  () => import("../features/documents/UploadContainer"),
  "UploadContainer",
);
const LabOrderApprovalContainer = route(
  () => import("../features/approvals/LabOrderApprovalContainer"),
  "LabOrderApprovalContainer",
);
const PreviewPage = route(() => import("../pages/preview/PreviewPage"), "PreviewPage");

function SuspenseFallback() {
  return (
    <div className="page">
      <Skeleton className="h-8 w-1/3" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

export function AppRouter() {
  return (
    <Suspense fallback={<SuspenseFallback />}>
      <Routes>
        <Route element={<RootLayout />}>
          <Route
            path={ROUTES.login}
            element={
              <GuestRoute>
                <LoginContainer />
              </GuestRoute>
            }
          />
          <Route
            path={ROUTES.register}
            element={
              <GuestRoute>
                <RegisterContainer />
              </GuestRoute>
            }
          />
          <Route path={ROUTES.forgotPassword} element={<ForgotPasswordContainer />} />
          <Route path={ROUTES.resetPassword} element={<ResetPasswordContainer />} />

          <Route
            path={ROUTES.onboarding}
            element={
              <ProtectedRoute roles={PATIENT_ROLES}>
                <OnboardingContainer />
              </ProtectedRoute>
            }
          />
          <Route
            path={ROUTES.chat}
            element={
              <ProtectedRoute roles={PATIENT_ROLES}>
                <TriageContainer />
              </ProtectedRoute>
            }
          />
          <Route
            path={ROUTES.assistant}
            element={
              <ProtectedRoute roles={PATIENT_ROLES}>
                <ChatbotContainer />
              </ProtectedRoute>
            }
          />
          <Route
            path={ROUTES.booking}
            element={
              <ProtectedRoute roles={PATIENT_ROLES}>
                <BookingContainer />
              </ProtectedRoute>
            }
          />
          <Route
            path={ROUTES.portal}
            element={
              <ProtectedRoute roles={PATIENT_ROLES}>
                <VisitListContainer />
              </ProtectedRoute>
            }
          />
          <Route
            path="/visit/:id"
            element={
              <ProtectedRoute roles={[...PATIENT_ROLES, ...DOCTOR_STAFF_ROLES]}>
                <VisitContainer />
              </ProtectedRoute>
            }
          />

          <Route
            path={ROUTES.doctorHome}
            element={
              <ProtectedRoute roles={CLINICAL_ROLES}>
                <VisitListContainer />
              </ProtectedRoute>
            }
          />
          <Route
            path="/doctor/patient/:id"
            element={
              <ProtectedRoute roles={DOCTOR_STAFF_ROLES}>
                {/* Interim: UploadContainer wired directly here for CP2.
                    A future PatientChartContainer will own this route and
                    compose the upload pipeline alongside the rest of the
                    patient chart. */}
                <UploadContainer />
              </ProtectedRoute>
            }
          />
          <Route
            path="/doctor/visit/:id"
            element={
              <ProtectedRoute roles={DOCTOR_STAFF_ROLES}>
                <VisitContainer />
              </ProtectedRoute>
            }
          />
          <Route
            path={ROUTES.doctorQueue}
            element={
              <ProtectedRoute roles={CLINICAL_ROLES}>
                <QueueBoardContainer />
              </ProtectedRoute>
            }
          />
          <Route
            path="/doctor/lab-order/:id"
            element={
              <ProtectedRoute roles={DOCTOR_STAFF_ROLES}>
                <LabOrderApprovalContainer />
              </ProtectedRoute>
            }
          />

          {isDev && <Route path={ROUTES.preview} element={<PreviewPage />} />}

          <Route path="/" element={<Navigate to={ROUTES.login} replace />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
