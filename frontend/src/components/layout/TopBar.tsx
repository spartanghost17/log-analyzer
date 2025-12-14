export const TopBar = () => {
  return (
    <header className="h-16 bg-white dark:bg-surface-darker border-b border-gray-200 dark:border-gray-800 flex items-center justify-between px-6 z-10">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2 text-gray-900 dark:text-white font-semibold text-lg">
          <span className="material-icons-outlined text-primary">psychology</span>
          Synaps
        </div>
        <div className="h-6 w-px bg-gray-300 dark:bg-gray-700 mx-2"></div>
        <div className="relative hidden md:block">
          <span className="material-icons-outlined absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-lg">search</span>
          <input
            className="pl-10 pr-4 py-1.5 bg-gray-100 dark:bg-[#1C1E26] border border-transparent dark:border-gray-700 rounded-md text-sm text-gray-900 dark:text-gray-300 placeholder-gray-500 focus:ring-1 focus:ring-primary focus:border-primary focus:bg-white dark:focus:bg-[#252833] w-64 transition-all"
            placeholder="Global search..."
            type="text"
          />
        </div>
      </div>
      <div className="flex items-center gap-4">
        <button className="relative p-2 text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">
          <span className="material-icons-outlined">notifications</span>
          <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-red-500 border border-white dark:border-surface-darker"></span>
        </button>
        <button className="p-2 text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors">
          <span className="material-icons-outlined">help_outline</span>
        </button>
      </div>
    </header>
  );
};
