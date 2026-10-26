
"use client";

import { useEffect, useState } from "react";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { api } from "@/lib/api";

type Category = {
  id: string;
  code: string;
  name: string;
  distance_km: number;
  slots_left: number;
  is_full: boolean;
};

const STORAGE_KEY = "ekitirun-registration";

const registrationSchema = z.object({
  first_name: z.string().trim().min(2, "Enter your first name."),
  last_name: z.string().trim().min(2, "Enter your last name."),
  gender: z.enum(["M", "F"], {
  required_error: "Select your gender.",
  invalid_type_error: "Select your gender.",
}),
  date_of_birth: z.string().min(1, "Enter your date of birth."),
  email: z.union([
    z.literal(""),
    z.string().email("Enter a valid email address."),
  ]),
  phone: z.string().min(10, "Enter a valid Nigerian phone number."),
  category_id: z.string().min(1, "Choose a race category."),
  emergency_contact_name: z.string().trim().min(2, "Enter the contact's name."),
  emergency_contact_phone: z.string().min(10, "Enter a valid phone number."),
});

type FormValues = z.infer<typeof registrationSchema>;

const emptyValues: FormValues = {
  first_name: "",
  last_name: "",
  gender: "M",
  date_of_birth: "",
  email: "",
  phone: "",
  category_id: "",
  emergency_contact_name: "",
  emergency_contact_phone: "",
};

function normalizeNigerianPhone(value: string) {
  const digits = value.replace(/\D/g, "");

  if (digits.startsWith("234")) return `+${digits}`;
  if (digits.startsWith("0")) return `+234${digits.slice(1)}`;

  return value.startsWith("+") ? value : `+234${digits}`;
}

function isValidNigerianPhone(value: string) {
  return /^\+234[789]\d{9}$/.test(normalizeNigerianPhone(value));
}

function calculateAge(dateOfBirth: string) {
  const birth = new Date(`${dateOfBirth}T00:00:00`);
  if (Number.isNaN(birth.getTime())) return 0;

  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();

  if (
    today.getMonth() < birth.getMonth() ||
    (today.getMonth() === birth.getMonth() &&
      today.getDate() < birth.getDate())
  ) {
    age--;
  }

  return age;
}

export default function RegistrationForm() {
  const [step, setStep] = useState(0);
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  const [categoriesError, setCategoriesError] = useState("");
  const [saved, setSaved] = useState(false);

  const {
    register,
    handleSubmit,
    trigger,
    watch,
    getValues,
    reset,
    setError,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(registrationSchema),
    defaultValues: emptyValues,
    mode: "onTouched",
  });

  const values = watch();

  useEffect(() => {
    try {
      const savedValues = sessionStorage.getItem(STORAGE_KEY);
      if (savedValues) {
        reset({ ...emptyValues, ...JSON.parse(savedValues) });
        setSaved(true);
      }
    } catch {
      sessionStorage.removeItem(STORAGE_KEY);
    }
  }, [reset]);

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(values));
    } catch {
      // The form can still be used if session storage is unavailable.
    }
  }, [values]);

  async function loadCategories() {
    setCategoriesLoading(true);
    setCategoriesError("");

    try {
      // Temporary compatibility bridge: the backend has not published
      // this endpoint in OpenAPI yet. Replace the cast after regeneration.
      const result = await api.GET("/categories" as never);
      const response = result as unknown as {
        data?: Category[];
        error?: { detail?: string };
      };

      if (response.error || !response.data) {
        throw new Error(response.error?.detail || "Could not load categories.");
      }

      setCategories(response.data);
    } catch {
      setCategoriesError(
        "We couldn't load race categories. The category service may not be ready yet.",
      );
    } finally {
      setCategoriesLoading(false);
    }
  }

  useEffect(() => {
    void loadCategories();
  }, []);

  async function nextStep() {
    const fieldsByStep: (keyof FormValues)[][] = [
      ["first_name", "last_name", "gender", "date_of_birth", "email", "phone"],
      ["category_id"],
      ["emergency_contact_name", "emergency_contact_phone"],
    ];

    const valid = await trigger(fieldsByStep[step]);

    if (!valid) return;

    if (step === 0 && !isValidNigerianPhone(getValues("phone"))) {
      setError("phone", {
        type: "validate",
        message: "Use a valid Nigerian number, e.g. 08012345678.",
      });
      return;
    }

    if (
      step === 2 &&
      !isValidNigerianPhone(getValues("emergency_contact_phone"))
    ) {
      setError("emergency_contact_phone", {
        type: "validate",
        message: "Use a valid Nigerian number, e.g. 08012345678.",
      });
      return;
    }

    if (step === 0 && calculateAge(getValues("date_of_birth")) < 18) {
      // The official race-day date still needs to be confirmed by the team.
      // This provisional check uses today's date until that date is supplied.
      setError("date_of_birth", {
        type: "validate",
        message: "You must be at least 18 for Full or Half Marathon eligibility.",
      });
      return;
    }

    setStep((current) => Math.min(current + 1, 3));
  }

  function continueToVerification() {
    const currentValues = getValues();

    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(currentValues));
    } catch {
      // Continue even if browser storage is unavailable.
    }

    window.location.href = "/register/verify";
  }

  function editStep(target: number) {
    setStep(target);
  }

  const selectedCategory = categories.find(
    (category) => category.id === values.category_id,
  );

  const inputClass =
    "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-3 text-base text-slate-900 outline-none focus:border-blue-600 focus:ring-2 focus:ring-blue-100";

  function fieldError(name: keyof FormValues) {
    const message = errors[name]?.message;
    return message ? (
      <p className="mt-1 text-sm text-red-600">{message}</p>
    ) : null;
  }

  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-8 text-slate-900 sm:py-12">
      <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">
        Ekiti Marathon
      </p>
      <h1 className="mt-2 text-3xl font-bold">Runner registration</h1>
      <p className="mt-2 text-slate-600">
        Complete each step to register for race day.
      </p>

      <div className="mt-6 grid grid-cols-4 gap-2" aria-label="Registration progress">
        {["Details", "Category", "Emergency", "Review"].map((label, index) => (
          <div key={label}>
            <div
              className={`h-2 rounded-full ${
                index <= step ? "bg-blue-700" : "bg-slate-200"
              }`}
            />
            <p className="mt-2 text-xs text-slate-600 sm:text-sm">
              {index + 1}. {label}
            </p>
          </div>
        ))}
      </div>

      <form
        className="mt-8 space-y-6"
        onSubmit={handleSubmit(continueToVerification)}
      >
        {step === 0 && (
          <section className="space-y-4">
            <h2 className="text-xl font-semibold">Your details</h2>

            <div>
              <label className="text-sm font-medium">First name</label>
              <input autoComplete="given-name" className={inputClass} {...register("first_name")} />
              {fieldError("first_name")}
            </div>

            <div>
              <label className="text-sm font-medium">Last name</label>
              <input autoComplete="family-name" className={inputClass} {...register("last_name")} />
              {fieldError("last_name")}
            </div>

            <div>
              <label className="text-sm font-medium">Gender</label>
              <select className={inputClass} {...register("gender")}>
                <option value="M">Male</option>
                <option value="F">Female</option>
              </select>
              {fieldError("gender")}
            </div>

            <div>
              <label className="text-sm font-medium">Date of birth</label>
              <input
                type="date"
                max={new Date().toISOString().slice(0, 10)}
                className={inputClass}
                {...register("date_of_birth")}
              />
              {fieldError("date_of_birth")}
            </div>

            <div>
              <label className="text-sm font-medium">Email (optional)</label>
              <input type="email" autoComplete="email" className={inputClass} {...register("email")} />
              {fieldError("email")}
            </div>

            <div>
              <label className="text-sm font-medium">Phone number</label>
              <input
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                placeholder="08012345678"
                className={inputClass}
                {...register("phone")}
              />
              <p className="mt-1 text-xs text-slate-500">
                Nigerian numbers starting with 080, 081, 090, etc. are accepted.
              </p>
              {fieldError("phone")}
            </div>
          </section>
        )}

        {step === 1 && (
          <section className="space-y-4">
            <h2 className="text-xl font-semibold">Choose your race category</h2>

            {categoriesLoading && (
              <div className="space-y-3" aria-label="Loading categories">
                {[1, 2, 3].map((item) => (
                  <div key={item} className="h-24 animate-pulse rounded-xl bg-slate-100" />
                ))}
              </div>
            )}

            {!categoriesLoading && categoriesError && (
              <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
                <p className="text-sm text-amber-900">{categoriesError}</p>
                <button
                  type="button"
                  onClick={() => void loadCategories()}
                  className="mt-3 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                >
                  Retry
                </button>
              </div>
            )}

            {!categoriesLoading && !categoriesError && categories.length === 0 && (
              <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-600">
                No race categories are available yet.
              </p>
            )}

            {!categoriesLoading &&
              !categoriesError &&
              categories.map((category) => (
                <label
                  key={category.id}
                  className={`block rounded-xl border p-4 ${
                    category.is_full
                      ? "cursor-not-allowed border-slate-200 bg-slate-50 opacity-60"
                      : values.category_id === category.id
                        ? "border-blue-700 bg-blue-50"
                        : "border-slate-300"
                  }`}
                >
                  <span className="flex items-start gap-3">
                    <input
                      type="radio"
                      value={category.id}
                      disabled={category.is_full}
                      className="mt-1"
                      {...register("category_id")}
                    />
                    <span className="flex-1">
                      <span className="block font-semibold">{category.name}</span>
                      <span className="mt-1 block text-sm text-slate-600">
                        {category.distance_km} km ·{" "}
                        {category.is_full
                          ? "Full"
                          : `${category.slots_left} slots left`}
                      </span>
                    </span>
                  </span>
                </label>
              ))}

            {fieldError("category_id")}
          </section>
        )}

        {step === 2 && (
          <section className="space-y-4">
            <h2 className="text-xl font-semibold">Emergency contact</h2>
            <p className="text-sm text-slate-600">
              Who should the race team contact in an emergency?
            </p>

            <div>
              <label className="text-sm font-medium">Contact name</label>
              <input autoComplete="name" className={inputClass} {...register("emergency_contact_name")} />
              {fieldError("emergency_contact_name")}
            </div>

            <div>
              <label className="text-sm font-medium">Contact phone</label>
              <input
                type="tel"
                inputMode="tel"
                placeholder="08012345678"
                className={inputClass}
                {...register("emergency_contact_phone")}
              />
              {fieldError("emergency_contact_phone")}
            </div>
          </section>
        )}

        {step === 3 && (
          <section className="space-y-4">
            <h2 className="text-xl font-semibold">Review your details</h2>
            <p className="text-sm text-slate-600">
              Check your information before continuing to phone verification.
            </p>

            {[
              { title: "Your details", target: 0, lines: [
                `${values.first_name} ${values.last_name}`,
                values.gender === "M" ? "Male" : "Female",
                `Date of birth: ${values.date_of_birth}`,
                values.email || "No email provided",
                normalizeNigerianPhone(values.phone),
              ] },
              { title: "Race category", target: 1, lines: [
                selectedCategory?.name || "No category selected",
              ] },
              { title: "Emergency contact", target: 2, lines: [
                values.emergency_contact_name,
                normalizeNigerianPhone(values.emergency_contact_phone),
              ] },
            ].map((section) => (
              <div key={section.title} className="rounded-xl border border-slate-200 p-4">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold">{section.title}</h3>
                  <button
                    type="button"
                    onClick={() => editStep(section.target)}
                    className="text-sm font-semibold text-blue-700 underline"
                  >
                    Edit
                  </button>
                </div>
                {section.lines.map((line) => (
                  <p key={line} className="mt-2 break-words text-sm text-slate-600">
                    {line}
                  </p>
                ))}
              </div>
            ))}
          </section>
        )}

        <div className="flex gap-3 border-t border-slate-200 pt-5">
          {step > 0 && (
            <button
              type="button"
              onClick={() => setStep((current) => current - 1)}
              className="min-h-12 flex-1 rounded-lg border border-slate-300 px-4 py-3 font-semibold"
            >
              Back
            </button>
          )}

          {step < 3 ? (
            <button
              type="button"
              onClick={() => void nextStep()}
              className="min-h-12 flex-1 rounded-lg bg-blue-700 px-4 py-3 font-semibold text-white hover:bg-blue-800"
            >
              Next
            </button>
          ) : (
            <button
              type="submit"
              className="min-h-12 flex-1 rounded-lg bg-blue-700 px-4 py-3 font-semibold text-white hover:bg-blue-800"
            >
              Continue to verification
            </button>
          )}
        </div>

        {saved && (
          <p className="text-center text-xs text-slate-500">
            Your form progress is saved in this browser session.
          </p>
        )}
      </form>
    </main>
  );
}
