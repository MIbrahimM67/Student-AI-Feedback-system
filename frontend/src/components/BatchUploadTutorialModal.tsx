import React, { useState } from "react";
import { ChevronRight, FolderArchive, Sparkles, TerminalSquare, X } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";

interface TutorialModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const BatchUploadTutorialModal: React.FC<TutorialModalProps> = ({ isOpen, onClose }) => {
  const [step, setStep] = useState(0);

  if (!isOpen) return null;

  const slides = [
    {
      icon: <FolderArchive className="w-6 h-6 text-[var(--color-accent)]" />,
      title: "Master ZIP Structure",
      description: "Upload one ZIP. Inside it, each student should have a folder containing their assignment files.",
      example: "Master_Batch.zip\n|-- John_Doe/\n|   |-- main.cpp\n|   `-- utils.h\n`-- Jane_Smith/\n    `-- index.html",
    },
    {
      icon: <TerminalSquare className="w-6 h-6 text-[var(--color-success)]" />,
      title: "Input Hints",
      description: "For coding tasks, provide an input hint so the grader can produce useful sandbox tests.",
      example: "Hint: numeric array of length 5\nGenerated checks: normal values, negative values, edge cases",
    },
    {
      icon: <Sparkles className="w-6 h-6 text-[var(--color-warning)]" />,
      title: "Rubric-Aligned Results",
      description: "The pipeline reads files, runs available checks, and returns feedback organized by student and rubric criteria.",
      example: "Supports C++, Python, Java, and static analysis for web projects.",
    },
  ];

  const handleNext = () => {
    if (step < slides.length - 1) setStep(step + 1);
    else onClose();
  };

  const handlePrev = () => {
    if (step > 0) setStep(step - 1);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 12 }}
        className="relative w-full max-w-lg overflow-hidden border border-[var(--color-rule)] bg-[var(--color-surface)] shadow-[var(--shadow-panel)]"
      >
        <button
          onClick={onClose}
          className="absolute right-4 top-4 z-10 bg-[var(--color-paper-2)] p-2 text-[var(--color-muted)] hover:text-[var(--color-ink)]"
          title="Close"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="p-7">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -16 }}
              transition={{ duration: 0.18 }}
              className="flex flex-col items-start"
            >
              <div className="mb-5 flex h-14 w-14 items-center justify-center border border-[var(--color-rule)] bg-[var(--color-paper-2)]">
                {slides[step].icon}
              </div>
              <h2 className="mb-3 text-2xl font-bold text-[var(--color-ink)]">{slides[step].title}</h2>
              <p className="mb-6 text-sm font-medium leading-7 text-[var(--color-muted)]">
                {slides[step].description}
              </p>

              <div className="w-full border border-[var(--color-ink)] bg-[#171717] p-4 text-left font-mono text-xs leading-6 text-[var(--color-ink)]">
                <pre className="whitespace-pre-wrap font-mono">{slides[step].example}</pre>
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="flex items-center justify-between border-t border-[var(--color-rule)] bg-[var(--color-paper-2)] p-5">
          <div className="flex gap-2">
            {slides.map((_, i) => (
              <div
                key={i}
                className={`h-2 transition-all duration-300 ${i === step ? "w-6 bg-[var(--color-accent)]" : "w-2 bg-[var(--color-rule-2)]"}`}
              />
            ))}
          </div>

          <div className="flex gap-3">
            {step > 0 ? (
              <button onClick={handlePrev} className="px-4 py-2 text-xs font-bold text-[var(--color-muted)] hover:text-[var(--color-ink)]">
                Back
              </button>
            ) : (
              <button onClick={onClose} className="px-4 py-2 text-xs font-bold text-[var(--color-muted)] hover:text-[var(--color-ink)]">
                Skip
              </button>
            )}
            <button
              onClick={handleNext}
              className="flex items-center gap-1.5 bg-[var(--color-accent)] px-6 py-2.5 text-xs font-extrabold text-[var(--color-accent-ink)] hover:bg-[var(--color-accent-2)]"
            >
              {step === slides.length - 1 ? "Done" : "Next"}
              {step !== slides.length - 1 && <ChevronRight className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
};
