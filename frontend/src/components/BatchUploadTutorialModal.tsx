import React, { useState } from "react";
import { FolderArchive, TerminalSquare, Sparkles, X, ChevronRight, ChevronLeft } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface TutorialModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const BatchUploadTutorialModal: React.FC<TutorialModalProps> = ({ isOpen, onClose }) => {
  const [step, setStep] = useState(0);

  if (!isOpen) return null;

  const slides = [
    {
      icon: <FolderArchive className="w-12 h-12 text-indigo-500" />,
      title: "The Master ZIP Structure",
      description: "To batch process multiple students, upload a single Master .zip file. Inside this zip, each student should have their own folder containing their assignment files.",
      example: "📁 Master_Batch.zip\n ├── 📁 John_Doe/\n │    ├── main.cpp\n │    └── utils.h\n └── 📁 Jane_Smith/\n      └── index.html",
    },
    {
      icon: <TerminalSquare className="w-12 h-12 text-emerald-500" />,
      title: "Autonomous STDIN Tests",
      description: "If you are assigning coding tasks, you can provide an 'Input Hint'. Our AI uses this hint to autonomously generate and run edge-case tests against every student's code.",
      example: "Hint Example: 'numeric array of length 5'\nThe AI will generate 3 test cases (e.g. standard array, negative numbers, edge cases) and run them securely in the terminal sandbox.",
    },
    {
      icon: <Sparkles className="w-12 h-12 text-amber-500" />,
      title: "AI Specialist Grading",
      description: "Our system compiles multi-file projects automatically. It reads all source files, runs the test cases, and provides detailed, rubic-aligned feedback per student.",
      example: "Supports multi-file compilation out-of-the-box for C++, Python, and Java. For Web projects (HTML/JS/CSS), it uses pure static analysis.",
    }
  ];

  const handleNext = () => {
    if (step < slides.length - 1) {
      setStep(step + 1);
    } else {
      onClose();
    }
  };

  const handlePrev = () => {
    if (step > 0) setStep(step - 1);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <motion.div 
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        className="relative w-full max-w-lg bg-white dark:bg-slate-900 rounded-3xl shadow-2xl overflow-hidden border border-slate-200 dark:border-slate-800"
      >
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-full transition-colors z-10"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="p-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
              className="flex flex-col items-center text-center"
            >
              <div className="p-4 bg-slate-50 dark:bg-slate-950 rounded-full border border-slate-100 dark:border-slate-800 shadow-sm mb-6">
                {slides[step].icon}
              </div>
              <h2 className="text-2xl font-extrabold text-slate-800 dark:text-slate-100 mb-3">
                {slides[step].title}
              </h2>
              <p className="text-sm font-medium text-slate-500 dark:text-slate-400 leading-relaxed mb-6">
                {slides[step].description}
              </p>
              
              <div className="w-full text-left bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl p-4 font-mono text-xs text-slate-600 dark:text-slate-300 leading-relaxed shadow-inner">
                <pre className="whitespace-pre-wrap font-mono">{slides[step].example}</pre>
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="flex items-center justify-between p-6 bg-slate-50 dark:bg-slate-950 border-t border-slate-100 dark:border-slate-800">
          <div className="flex gap-2">
            {slides.map((_, i) => (
              <div 
                key={i} 
                className={`w-2 h-2 rounded-full transition-all duration-300 ${i === step ? "bg-indigo-600 w-6" : "bg-slate-300 dark:bg-slate-700"}`}
              />
            ))}
          </div>

          <div className="flex gap-3">
            {step > 0 ? (
              <button
                onClick={handlePrev}
                className="px-4 py-2 text-xs font-bold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors"
              >
                Back
              </button>
            ) : (
              <button
                onClick={onClose}
                className="px-4 py-2 text-xs font-bold text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
              >
                Skip Tutorial
              </button>
            )}
            <button
              onClick={handleNext}
              className="flex items-center gap-1.5 px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-extrabold rounded-xl shadow-lg shadow-indigo-200 dark:shadow-none transition-all"
            >
              {step === slides.length - 1 ? "Got it!" : "Next"}
              {step !== slides.length - 1 && <ChevronRight className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
};
