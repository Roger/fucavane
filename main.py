from defuse.fs import FS
import fucavane

fs = FS.get()

if __name__ == '__main__':
    fs.parse(values=fs, errex=1)
    fs.main()
