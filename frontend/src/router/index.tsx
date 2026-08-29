import { Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { RootLayout } from "../app/RootLayout";
import { NotFound } from "../app/NotFound";
import { VisitListContainer } from "../features/visits/VisitListContainer";
import { Skeleton } from "../components/ui/Skeleton";
import { ProtectedRoute } from "./ProtectedRoute";
import { ROUTES, PATIENT_ROLES, DOCTOR_STAFF_ROLES, CLINICAL_ROLES } from "./routes";
import { LoginContainer } from "../features/auth/LoginContainer";
import { RegisterContainer } from "../features/auth/RegisterContainer";
import { ForgotPasswordContainer } from "../features/auth/ForgotPasswordContainer";
import { ResetPasswordContainer } from "../features/auth/ResetPasswordContainer";
import { OnboardingContainer } from "../features/onboarding/OnboardingContainer";
import { TriageContainer } from "../features/triage/TriageContainer";
import { BookingContainer } from "../features/booking/BookingContainer";
import { QueueBoardContainer } from "../features/queue/QueueBoardContainer";
import { UploadContainer } from "../features/documents/UploadContainer";
import { LabOrderApprovalContainer } from "../features/approvals/LabOrderApprovalContainer";
import { ChatbotContainer } from "../features/chatbot/ChatbotContainer";
import { VisitContainer } from "../features/visit/VisitContainer";
import { PreviewPage } from "../pages/preview/PreviewPage";

const isDev = import.meta.env.DEV;

function SuspenseFallback() {
  return (
    <div className="flex flex-col gap-3 p-6">
      <Skeleton className="h-10 w-2/3" />
      <Skeleton className="h-10 w-1/2" />
    </div>
  );
}

export function AppRouter() {
  return (
    <Suspense fallback={<SuspenseFallback />}>
      <Routes>
        <Route element={<RootLayout />}>
          <Route path={ROUTES.login} element={<LoginContainer />} />
          <Route path={ROUTES.register} element={<RegisterContainer />} />
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
