import os, json
from abc import ABC, abstractmethod


class IMemo(ABC):
    @abstractmethod
    def compare(self, other_memo):
        ...

    @property
    @abstractmethod
    def memo(self):
        ...
    
    def save_memo(self, fname):
        os.makedirs(os.path.dirname(fname), exist_ok=True)
        with open(fname, "w") as f:
            json.dump(self.memo, f)
    
    def compare_to_saved(self, fname):
        if not os.path.exists(fname):
            return False

        with open(fname) as f:
            other = json.load(f)

        return self.compare(other)
    

class IMemoAtom(ABC):
    @property
    @abstractmethod
    def memo_value(self):
        """
        Returns:
            object to be memoized
        """
        ...


class ILazyMemoValue(ABC):
    @abstractmethod
    def __call__(self):
        """
        Returns:
            object to be memoized.
        """
        ...
